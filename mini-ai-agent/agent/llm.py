import json
import logging
import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from ollama import Client

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

_client = Client(host=OLLAMA_HOST)

SYSTEM_PROMPT = """You are the router of a small task agent.
Read the user request and return ONLY a JSON object.

Allowed actions:
- "email": the user explicitly wants to send an email.
- "report": the user explicitly wants to generate a report.
- "both": the user explicitly wants an email AND a report.
- "unknown": the request is not about sending an email or generating a report.

Rules:
- The user may write in English or French, with spelling mistakes.
  "rapport" / "resume" / "synthese" mean report.
  "courriel" / "mail" mean email.
  "generate", "create", "write", "make" + report/summary/analysis mean report.
- Only use "email", "report" or "both" when the request clearly asks for it.
- Never invent an action. A question that is not about email or report (for
  example "What is the weather today?") MUST be "unknown".
- Do not turn a general question into a report.

JSON shape:
{"action": "email|report|both|unknown", "to": "", "subject": "", "body": "", "title": "", "content": ""}

Fill the email fields for "email" and "both".
Fill the report fields for "report" and "both".
Keep subject, body, title and content short (one or two sentences).
Return JSON only, with no markdown and no explanation."""


def _normalize(text: str) -> str:
    """Lowercase, strip accents and reduce punctuation to spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9@.+-]+", " ", text.lower()).strip()


def _fuzzy_has(tokens: list[str], candidates: set[str], cutoff: float = 0.82) -> bool:
    """Match a token to a keyword, tolerating common typos."""
    for token in tokens:
        if token in candidates:
            return True
        if len(token) < 5:
            continue
        if any(SequenceMatcher(None, token, word).ratio() >= cutoff for word in candidates):
            return True
    return False


def _detect_intents(message: str) -> tuple[bool, bool]:
    """Detect explicit email/report intent, including French and typos."""
    text = _normalize(message)
    tokens = text.split()

    email_nouns = {
        "email",
        "emails",
        "mail",
        "mails",
        "courriel",
        "courriels",
    }
    email_verbs = {
        "send",
        "sends",
        "sent",
        "envoyer",
        "envoie",
        "envoye",
        "envoyes",
        "envoyee",
        "envoyees",
        "envoyez",
        "notify",
        "notifie",
        "notifier",
        "notification",
    }
    report_nouns = {
        "report",
        "reports",
        "rapport",
        "rapports",
        "summary",
        "summaries",
        "summarize",
        "summarise",
        "resume",
        "analysis",
        "analyse",
        "analyser",
        "analyses",
        "synthesis",
        "synthese",
        "document",
        "documents",
        "pdf",
        "html",
        "chart",
        "charts",
        "graph",
        "graphs",
        "dashboard",
        "bilan",
        "presentation",
    }

    wants_email = _fuzzy_has(tokens, email_nouns, 0.80) or _fuzzy_has(
        tokens, email_verbs, 1.0
    )
    wants_report = _fuzzy_has(tokens, report_nouns, 0.80)

    if "compte" in tokens and "rendu" in tokens:
        wants_report = True

    return wants_email, wants_report


def _fallback_action(message: str) -> str:
    """Keyword-based fallback used when the model output is not usable."""
    wants_email, wants_report = _detect_intents(message)

    if wants_email and wants_report:
        return "both"
    if wants_email:
        return "email"
    if wants_report:
        return "report"
    return "unknown"


def _validate_action(action: str, message: str) -> str:
    """Reject LLM actions that are not supported by explicit intent keywords."""
    wants_email, wants_report = _detect_intents(message)

    if wants_email and wants_report:
        return "both"
    if action == "email" and wants_email:
        return "email"
    if action == "report" and wants_report:
        return "report"
    return _fallback_action(message)


def _extract_email(message: str) -> str:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", message or "")
    return match.group(0) if match else ""


def _topic_from_message(message: str) -> str:
    """Turn a command such as 'generate a report about sales' into 'Sales'."""
    normalized = _normalize(message)
    articles = {
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "un",
        "une",
        "le",
        "la",
        "les",
        "des",
        "ce",
        "cette",
        "ces",
    }

    # Prefer the explicit topic after a report noun, even inside a long request
    # such as "send an email ... and generate a report about X".
    report_match = re.search(
        r"\b(?:report|rapport|summary|resume|analysis|analyse|synthese|"
        r"document|pdf|html|compte\s+rendu)\b\s+"
        r"(?:about|on|of|sur|de|du|des|concernant)\s+(.+)",
        normalized,
    )
    if report_match:
        words = report_match.group(1).split()
        while words and words[0] in articles:
            words.pop(0)
        topic = " ".join(words).capitalize()
        return "" if topic.lower() in {"pdf", "html", "document", "report", "rapport"} else topic

    email_match = re.search(
        r"\b(?:email|mail|courriel)\b(?:\s+to\s+\S+)?\s+"
        r"(?:about|on|of|sur|de|du|des|concernant)\s+(.+)",
        normalized,
    )
    if email_match:
        words = email_match.group(1).split()
        while words and words[0] in articles:
            words.pop(0)
        return " ".join(words).capitalize()

    words = normalized.split()
    generation_verbs = {
        "generate",
        "create",
        "make",
        "write",
        "build",
        "produce",
        "prepare",
        "give",
        "fais",
        "faire",
        "genere",
        "generer",
        "redige",
        "rediger",
        "cree",
        "creer",
        "ecris",
        "ecrire",
        "produis",
        "produire",
        "prepare",
        "preparer",
        "donne",
        "summarise",
        "summarize",
        "analyse",
        "analyser",
        "resume",
        "resumer",
    }
    report_nouns = {
        "report",
        "rapport",
        "summary",
        "resume",
        "analysis",
        "analyse",
        "synthese",
        "document",
        "pdf",
        "html",
    }
    prepositions = {"about", "on", "of", "sur", "de", "du", "des", "concernant"}

    while words and (
        words[0] in {"please", "svp", "me", "moi", "s", "il", "te", "plait"}
        or _fuzzy_has([words[0]], generation_verbs, 0.80)
    ):
        words.pop(0)
    while words and words[0] in articles:
        words.pop(0)
    if len(words) >= 3 and words[0] == "compte" and words[1] == "rendu":
        words = words[2:]
        if words and words[0] in prepositions:
            words.pop(0)
    elif len(words) >= 2 and _fuzzy_has([words[0]], report_nouns, 0.80):
        words.pop(0)
        if words and words[0] in prepositions:
            words.pop(0)
    while words and words[0] in articles:
        words.pop(0)

    topic = " ".join(words).capitalize()
    if topic.lower() in {"pdf", "html", "document", "report", "rapport"}:
        return ""
    return topic


def topic_from_message(message: str) -> str:
    """Public helper used to derive a short report/research topic."""
    return _topic_from_message(message)


def _keyword_result(message: str) -> dict[str, Any]:
    """Build a deterministic result when explicit keywords are present."""
    wants_email, wants_report = _detect_intents(message)
    if wants_email and wants_report:
        action = "both"
    elif wants_email:
        action = "email"
    elif wants_report:
        action = "report"
    else:
        action = "unknown"

    topic = _topic_from_message(message)
    report_title = topic or "Mini AI Agent Report"
    subject = topic or "Message from Mini AI Agent"

    return {
        "action": action,
        "data": {
            "to": _extract_email(message),
            "subject": subject,
            "body": message,
            "title": report_title,
            "content": message,
        },
    }


def classify_request(message: str) -> dict[str, Any]:
    """Classify a request, using fast deterministic keywords when possible."""
    wants_email, wants_report = _detect_intents(message)

    if wants_email or wants_report:
        result = _keyword_result(message)
        logging.info(
            "Keyword classification %r -> %s (LLM skipped)", message, result["action"]
        )
        return result

    data: dict[str, Any] = {}

    try:
        response = _client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            format="json",
            options={"temperature": 0},
        )
        raw = (
            response.message.content
            if hasattr(response, "message")
            else response["message"]["content"]
        )
        data = json.loads(raw)
    except Exception as exc:
        logging.warning("LLM classification failed, using keyword fallback: %s", exc)

    action = str(data.get("action", "")).strip().lower()
    action = _validate_action(action, message)

    return {"action": action, "data": data}


_RESEARCH_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "avec",
    "dans",
    "des",
    "est",
    "for",
    "from",
    "has",
    "have",
    "into",
    "les",
    "pour",
    "que",
    "qui",
    "the",
    "their",
    "this",
    "that",
    "une",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
    "your",
}

_RESEARCH_PROMPT = """You are a careful report writer.
Write a clear, natural answer using ONLY the verified draft and numbered source extracts.

Goal: a short, factual, human-readable report. Keep concrete facts such as dates,
names, places, platforms, numbers and awards. Remove generic filler.

Format (plain text):
- Direct answer: 2-3 sentences giving the most important facts first.
- Key facts: 4-5 bullet lines starting with "- ", each a distinct concrete fact.

Rules:
- Do not invent facts. If a requested value is missing, say so briefly.
- Do not write vague sentences like "has become a cultural phenomenon" unless the
  sources explicitly support them.
- Never mention "sources", "snippets", "retrieved", "pages", "according to" or include URLs.
- No markdown headings, no tables, no code fences.
"""


def _research_terms(query: str) -> set[str]:
    terms = {
        token
        for token in _normalize(query).split()
        if len(token) >= 3 and token not in _RESEARCH_STOPWORDS
    }
    return terms


_SOURCE_NOISE_RE = re.compile(
    r"(store|shop|buy|steam|amazon|ebay|download|price|deal|discount|"
    r"wishlist|cart|checkout|wasm|browser port|emulator|rom|apk|torrent|"
    r"cheat|mod menu|softonic|malavida)",
    re.IGNORECASE,
)

_FACT_DETAIL_RE = re.compile(
    r"\b(released?|release date|developer|developed|publisher|published|"
    r"genre|platforms?|playstation|xbox|windows|nintendo|steam|pc|"
    r"set in|follows|features?|players?|sales|sold|metascore|review|score|"
    r"award|created|designed|written|composed|mode|multiplayer|single-player|"
    r"story|protagonists?|missions?|fictional|entry)\b",
    re.IGNORECASE,
)

_MARKETING_RE = re.compile(
    r"(buy now|add to cart|sign in|log in|store home|privacy policy|"
    r"all rights reserved|experience entertainment blockbusters|"
    r"now available for|available for playstation|skip to content|"
    r"view desktop website|change language|report a translation problem|"
    r"community hub|points shop|wishlist|discovery queue|"
    r"subscribe|newsletter|cookie|advertisement|sponsored|shipping|"
    r"discount|price|reviews? \d|user reviews)",
    re.IGNORECASE,
)

_BAD_FACT_RE = re.compile(
    r"(reviews?\s*[-–|]|metacritic|summary|click here|read more|"
    r"buy now|available for|system requirements|screenshots|videos|"
    r"tags|price|shipping|community hub|points shop|guide|cheat|"
    r"walkthrough|beginner|cash card|virtual currency|shark card|"
    r"ign rating|rate game|howlongtobeat|leaderboard|checklists|"
    r"playlists|maps|reviews|users interact|franchises|steam deck|"
    r"preorder|not to be confused|now upgraded|stunning visuals|"
    r"faster loading|blockbuster|ever-evolving)",
    re.IGNORECASE,
)

_STRONG_FACT_RE = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(developed|published|released?|release date|"
    r"set in|follows|features?|platforms?|playstation|xbox|windows|"
    r"nintendo|sales|sold|award|protagonists?|missions?|multiplayer|"
    r"single-player|entry|series)\b",
    re.IGNORECASE,
)

_PLATFORM_RE = re.compile(
    r"\b(playstation(?:\s*\d)?|ps[345]|xbox(?:\s*(?:one|series\s*[xs]))?|"
    r"nintendo(?:\s*switch)?|switch|windows|pc|steam|mac|linux|ios|android)\b",
    re.IGNORECASE,
)


def _unsupported_entities(text: str, context: str) -> list[str]:
    context_lower = context.lower()
    missing: list[str] = []
    for match in _PLATFORM_RE.finditer(text):
        term = re.sub(r"\s+", " ", match.group(0).lower())
        if term not in context_lower and term not in missing:
            missing.append(term)
    return missing


def _source_relevance(query: str, source: dict[str, Any]) -> float:
    """Use the search engine score when available, else estimate overlap."""
    value = source.get("relevance")
    if isinstance(value, (int, float)):
        score = float(value)
    else:
        terms = _research_terms(query)
        title = set(_normalize(source.get("title", "")).split())
        url = set(_normalize(source.get("url", "")).split())
        snippet = set(_normalize(source.get("snippet", "")).split())
        score = 0.0
        for term in terms:
            if term in title:
                score += 4
            elif term in url:
                score += 2
            elif term in snippet:
                score += 1

    label = f"{source.get('title', '')} {source.get('url', '')}"
    if _SOURCE_NOISE_RE.search(label):
        score -= 8
    if "wikipedia.org/wiki/" in label:
        score += 6
    elif re.search(r"(metacritic|mobygames|imdb|britannica|official)", label, re.I):
        score += 2
    if re.search(r"(playstation\.com|microsoft\.com|xbox\.com|nintendo\.com)", label, re.I) and not re.search(
        r"(playstation|xbox|nintendo|microsoft)", query, re.IGNORECASE
    ):
        score -= 6
    return score


def _rank_sources(
    query: str, sources: list[dict[str, Any]], limit: int = 5
) -> list[dict[str, Any]]:
    scored = [
        (_source_relevance(query, source), order, source)
        for order, source in enumerate(sources)
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    if not scored:
        return []
    threshold = max(6.0, scored[0][0] * 0.65)
    kept = [row for row in scored if row[0] >= threshold]
    if len(kept) < 3:
        kept = scored[:3]
    return [source for _, _, source in kept[:limit]]


_WEATHER_HINT_RE = re.compile(
    r"(weather|forecast|temperature|temp(?:erature)?|meteo|météo|"
    r"rain|precip|wind|humidity|sunrise|sunset|uv|tomorrow|demain|today)",
    re.IGNORECASE,
)


def _is_weather_query(query: str) -> bool:
    return bool(_WEATHER_HINT_RE.search(query or ""))


_FACT_VALUE_RE = re.compile(
    r"(?P<value>"
    r"[+-]?\d{1,3}(?:[.,]\d+)?\s*(?:°\s?[CF]|deg(?:rees)?\s*[CF]|C|F)"
    r"|[+-]?\d{1,3}(?:[.,]\d+)?\s*%"
    r"|\d{1,3}(?:[.,]\d+)?\s*(?:km/?h|kph|mph|m/s|knots?|mm|cm|in|hPa|UV)"
    r"|\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b"
    r")"
)

_FACT_SENTENCE_RE = re.compile(
    r"\b(high|low|temperature|temp|rain|precipitation|chance of rain|"
    r"wind|humidity|sunrise|sunset|uv|feels like|conditions?|cloud|sunny|"
    r"clear|showers?|storm|thunder|snow|forecast)\b",
    re.IGNORECASE,
)


_EXTRACT_BOILERPLATE_RE = re.compile(
    r"(ad free|remove ads|read on|cookie|subscribe|sign in|log in|"
    r"download .*?app|book a timeslot|location search|darkmode|"
    r"all rights reserved|privacy policy|skip to main content|"
    r"official websites use|find articles by|doi:\s*10\.)",
    re.IGNORECASE,
)


def _chunk_words(text: str, size: int = 160) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in text.split():
        if current and length + len(word) + 1 > size:
            chunks.append(" ".join(current))
            current = []
            length = 0
        current.append(word)
        length += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _source_sentences(source: dict[str, Any]) -> list[str]:
    sentences: list[str] = []
    for key in ("text", "snippet"):
        value = str(source.get(key, "") or "")
        for part in re.split(r"(?<=[.!?])\s+|\n+", value):
            part = re.sub(r"\s+", " ", part).strip(" -")
            if not part or _EXTRACT_BOILERPLATE_RE.search(part):
                continue
            if len(part) <= 360:
                if len(part) >= 30:
                    sentences.append(part)
            else:
                sentences.extend(
                    chunk for chunk in _chunk_words(part) if len(chunk) >= 30
                )
    return sentences


_DATE_MARKER_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b\s+\d{1,2}[-/]\d{1,2}",
    re.IGNORECASE,
)


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "..."


def _clean_fragment(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip(" -|•")
    # drop leftover boilerplate fragments and broken punctuation runs
    text = re.sub(r"\b(AD FREE|Remove ads|Book a timeslot|Are you a hiker)\b.*", "", text, flags=re.I)
    text = re.sub(r"[?]{2,}", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -|•,;:")
    return text


def _dedupe_keep(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\W+", "", item.lower())
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _looks_like_day_dump(text: str) -> bool:
    return len(_DATE_MARKER_RE.findall(text)) >= 2 or len(re.findall(r"\b\d{1,2}\s*°\s?[CF]\b", text)) >= 4


_TEMP_RE = re.compile(r"([+-]?\d{1,2}(?:[.,]\d)?)\s*°\s?([CF])", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d{1,3})\s*%")
_WIND_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*(km/?h|kph|mph|m/s|knots?)", re.IGNORECASE)
_SUN_RE = re.compile(r"(\d{1,2}(?:[.,]\d)?)\s*h(?:ours?)?\b", re.IGNORECASE)


def _pick_tomorrow_segment(text: str) -> str:
    # try to isolate a "tomorrow/tmr" segment, else first day-like segment
    m = re.search(r"\b(?:Tomorrow|Tmr)\b[^A-Za-z]{0,30}(.{0,220}?)(?=\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b|$)", text, re.IGNORECASE)
    if m:
        return m.group(0)
    m = _DATE_MARKER_RE.search(text)
    if m:
        start = m.start()
        nxt = _DATE_MARKER_RE.search(text, m.end())
        end = nxt.start() if nxt else min(len(text), start + 220)
        return text[start:end]
    return text[:260]


def _fmt_num(value: object, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "?"


def _live_weather_answer(sources: list[dict[str, Any]]) -> str:
    for source in sources:
        data = source.get("weather")
        if not isinstance(data, dict):
            continue
        current = data.get("current") or {}
        daily = data.get("daily") or []
        location = data.get("location") or "the requested location"
        unit = current.get("temperature_unit") or "°C"
        wind_unit = current.get("wind_unit") or "km/h"
        condition = current.get("condition") or "current conditions"
        temp = _fmt_num(current.get("temperature"))
        apparent = _fmt_num(current.get("apparent"))
        humidity = _fmt_num(current.get("humidity"), 0)
        wind = _fmt_num(current.get("wind"))
        precip = _fmt_num(current.get("precipitation"))
        today_text = ""
        if daily:
            today = daily[0]
            today_text = (
                f" Today: {_fmt_num(today.get('low'))}{unit} to "
                f"{_fmt_num(today.get('high'))}{unit} with "
                f"{_fmt_num(today.get('chance'), 0)}% chance of precipitation."
            )
        direct = (
            f"Current conditions in {location}: {temp}{unit}, feels like "
            f"{apparent}{unit}, {condition}, with humidity at {humidity}% and "
            f"wind near {wind} {wind_unit}.{today_text}"
        )
        facts = [
            f"Current temperature: {temp}{unit} (feels like {apparent}{unit})",
            f"Conditions: {condition}",
            f"Humidity: {humidity}%",
            f"Wind: {wind} {wind_unit}",
            f"Precipitation: {precip} mm",
        ]
        for item in daily[:2]:
            facts.append(
                f"{item.get('date')}: {_fmt_num(item.get('low'))}{unit} to "
                f"{_fmt_num(item.get('high'))}{unit}, "
                f"{_fmt_num(item.get('chance'), 0)}% chance of precipitation"
            )
        lines = ["Direct answer:", direct, "", "Key facts:"]
        for fact in facts[:6]:
            lines.append(f"- {fact}")
        lines.extend(
            ["", "Details:", f"Live forecast data from Open-Meteo for {location}."]
        )
        return "\n".join(lines)
    return ""


def _extract_weather_answer(query: str, sources: list[dict[str, Any]]) -> str:
    live = _live_weather_answer(sources)
    if live:
        return live
    blobs: list[str] = []
    for source in sources:
        for key in ("text", "snippet"):
            val = _clean_fragment(str(source.get(key, "") or ""))
            if val and (re.search(r"\d", val) or _is_weather_query(val)):
                blobs.append(val)
    if not blobs:
        return ""

    # prefer blobs mentioning tomorrow/location-like terms
    q_terms = _research_terms(query)
    def bscore(b: str) -> tuple[int, int]:
        low = b.lower()
        return (1 if ("tomorrow" in low or "tmr" in low or "demain" in low) else 0,
                sum(1 for t in q_terms if t in low))

    blobs.sort(key=bscore, reverse=True)
    focus = _clean_fragment(_pick_tomorrow_segment(blobs[0])) if blobs else ""
    temps = _TEMP_RE.findall(focus)
    wind = _WIND_RE.search(focus)
    sun = _SUN_RE.search(focus)
    pct = _PCT_RE.findall(focus)

    # also scan other blobs for a chance-of-rain sentence
    rain_sentence = ""
    cond_sentence = ""
    for b in blobs[:6]:
        if not rain_sentence:
            m = re.search(r"([^.!?\n]{0,80}\b(?:chance of (?:rain|precipitation)|rain|shower|precipitation)\b[^.!?\n]{0,80})", b, re.IGNORECASE)
            if m and _PCT_RE.search(m.group(1)):
                rain_sentence = _clean_fragment(m.group(1))
        if not cond_sentence:
            m = re.search(r"([^.!?\n]{0,80}\b(?:sunny|clear|cloudy|overcast|thunder|storm|snow|fog|mist|partly)\b[^.!?\n]{0,80})", b, re.IGNORECASE)
            if m and len(m.group(1)) > 12:
                cond_sentence = _clean_fragment(m.group(1))

    direct_bits: list[str] = []
    if temps:
        # heuristic: first two temps often high/low
        if len(temps) >= 2:
            direct_bits.append(f"temperatures around {temps[0][0]}°{temps[0][1].upper()} / {temps[1][0]}°{temps[1][1].upper()}")
        else:
            direct_bits.append(f"temperature around {temps[0][0]}°{temps[0][1].upper()}")
    if rain_sentence:
        m = _PCT_RE.search(rain_sentence)
        if m:
            direct_bits.append(f"chance of rain about {m.group(1)}%")
    elif pct:
        # only use a % as rain chance if no explicit sentence; avoid random 0% from dumps
        pass
    if wind:
        direct_bits.append(f"wind near {wind.group(1)} {wind.group(2)}")
    if sun:
        direct_bits.append(f"about {sun.group(1)} h of sun")

    facts: list[str] = []
    if temps:
        if len(temps) >= 2:
            facts.append(f"High/Low: {temps[0][0]}°{temps[0][1].upper()} / {temps[1][0]}°{temps[1][1].upper()}")
        else:
            facts.append(f"Temperature: {temps[0][0]}°{temps[0][1].upper()}")
    if rain_sentence:
        facts.append(f"Precipitation: {_shorten(rain_sentence, 140)}")
    if wind:
        facts.append(f"Wind: {wind.group(1)} {wind.group(2)}")
    if sun:
        facts.append(f"Sunshine: about {sun.group(1)} hours")
    if cond_sentence:
        facts.append(f"Conditions: {_shorten(cond_sentence, 140)}")

    if not direct_bits and not facts:
        return ""

    if direct_bits:
        direct = f"For \"{_clean_fragment(query)}\": " + ", ".join(_dedupe_keep(direct_bits)) + "."
    else:
        direct = f"For \"{_clean_fragment(query)}\": the retrieved sources provide the following weather details."

    facts = _dedupe_keep(facts)[:6]
    if not facts:
        facts = ["Available details are limited in the retrieved sources."]

    lines = [
        "Direct answer:",
        _shorten(direct, 320),
        "",
        "Key facts:",
    ]
    for fact in facts:
        lines.extend([f"- {fact}", ""])
    lines.extend([
        "Details:",
        "These values are interpreted from the retrieved forecast sources for the requested day/location. "
        "If a specific value (e.g. exact hourly rain) is missing, it was not clearly available in the sources.",
    ])
    return "\n".join(lines).strip()


def _extractive_summary(query: str, sources: list[dict[str, Any]]) -> str:
    """Deterministic fallback: produce a readable, interpreted answer."""
    # weather/time-sensitive factual queries: try to interpret into a clear answer
    if _is_weather_query(query):
        weather_answer = _extract_weather_answer(query, sources)
        if weather_answer:
            return weather_answer

    terms = _research_terms(query)
    ranked_sources = _rank_sources(query, sources, limit=5)
    scored: list[tuple[float, int, str, int]] = []
    seen: set[str] = set()
    order = 0

    for source_index, source in enumerate(ranked_sources):
        for sentence_index, sentence in enumerate(_source_sentences(source)):
            sentence = _clean_fragment(sentence)
            if len(sentence) < 30:
                continue
            key = re.sub(r"\W+", "", sentence.lower())
            if not key or key in seen:
                continue
            seen.add(key)
            lower = sentence.lower()
            overlap = sum(1 for term in terms if term in lower)
            has_value = bool(
                _FACT_VALUE_RE.search(sentence)
                or re.search(r"\b(?:19|20)\d{2}\b", sentence)
                or re.search(r"\b\d{1,3}(?:[.,]\d+)?\b", sentence)
            )
            fact_hits = len(set(_FACT_DETAIL_RE.findall(sentence)))
            # penalize multi-day dumps and source-listing noise
            if _looks_like_day_dump(sentence):
                continue
            if re.search(
                r"hour by hour|everything you need to know|see the source|"
                r"click here|read more|learn more",
                lower,
            ):
                continue
            if _MARKETING_RE.search(sentence) and not re.search(
                r"\b(released?|release date|developer|publisher|metascore|"
                r"sales|sold|award|platforms?)\b",
                sentence,
                re.IGNORECASE,
            ):
                continue
            if _BAD_FACT_RE.search(sentence) and not re.search(
                r"\b(released?|release date|developer|publisher|sales|sold|award)\b",
                sentence,
                re.IGNORECASE,
            ):
                continue
            score = float(overlap * 3 + min(fact_hits, 3) * 2 + (2 if has_value else 0))
            score += max(0, 4 - source_index)
            if sentence_index < 3:
                score += 2
            if len(sentence) < 60:
                score -= 2
            if _MARKETING_RE.search(sentence):
                score -= 5
            if overlap == 0 and fact_hits == 0 and not has_value:
                continue
            if score <= 0:
                continue
            scored.append((score, order, sentence, source_index))
            order += 1

    scored.sort(key=lambda item: (-item[0], item[1]))

    candidates: list[str] = []
    source_counts: dict[int, int] = {}
    for _, _, sentence, source_index in scored:
        if source_counts.get(source_index, 0) >= 2:
            continue
        source_counts[source_index] = source_counts.get(source_index, 0) + 1
        candidates.append(sentence)
        if len(candidates) >= 7:
            break

    if not candidates:
        # fallback to cleaned snippets, still avoid dumps
        for source in ranked_sources:
            snip = _clean_fragment(str(source.get("snippet", "") or ""))
            if snip and not _looks_like_day_dump(snip):
                candidates.append(_shorten(snip, 260))
        candidates = _dedupe_keep(candidates)[:5]

    if not candidates:
        return ""

    direct = ""
    for sentence in _source_sentences(ranked_sources[0]):
        cleaned = _clean_fragment(sentence)
        if len(cleaned) >= 60 and re.search(r"\b(?:19|20)\d{2}\b", cleaned):
            direct = _shorten(cleaned, 340)
            break
    if not direct:
        direct = _shorten(candidates[0], 340)
    if len(direct) < 80 and len(candidates) > 1:
        direct = _shorten(f"{candidates[0]} {candidates[1]}", 440)

    direct_key = re.sub(r"\W+", "", direct.lower())
    facts = [
        _shorten(candidate, 240)
        for candidate in _dedupe_keep(candidates)
        if re.sub(r"\W+", "", candidate.lower()) != direct_key
    ][:5]
    if not facts:
        facts = [_shorten(candidates[0], 240)]

    lines = [
        "Direct answer:",
        direct,
        "",
        "Key facts:",
    ]
    for fact in facts[:6]:
        lines.extend([f"- {fact}", ""])
    detail = " ".join(_dedupe_keep(candidates[:3]))
    lines.extend([
        "Details:",
        _shorten(detail, 800) if detail else "Details were not clearly available in the retrieved sources.",
    ])
    return "\n".join(lines).strip()


def _clean_synthesis(value: str) -> str:
    text = value or ""
    text = re.sub(r"^```(?:text)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text)
        if part.strip()
    ]


def _limit_sentences(text: str, count: int) -> str:
    return " ".join(_split_sentences(text)[:count]).strip()


def _synthesis_sections(text: str) -> dict[str, str]:
    heading = re.compile(r"(?im)^\s*(Direct answer|Key facts|Details)\s*:\s*")
    matches = list(heading.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        key = match.group(1).lower()
        if key not in sections:
            sections[key] = text[match.end() : end].strip()
    return sections


def _fact_candidates(text: str, strict: bool = False) -> list[str]:
    facts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        for sentence in _split_sentences(line):
            sentence = _shorten(sentence, 220)
            if len(sentence.split()) < 7:
                continue
            if strict and not _STRONG_FACT_RE.search(sentence):
                continue
            if _BAD_FACT_RE.search(sentence):
                continue
            key = re.sub(r"\W+", "", sentence.lower())
            if key and key not in {
                re.sub(r"\W+", "", fact.lower()) for fact in facts
            }:
                facts.append(sentence)
    return facts


def _format_synthesis(text: str, fallback: str = "") -> str:
    """Keep the model output short, factual and free of duplicated paragraphs."""
    sections = _synthesis_sections(text)
    fallback_sections = _synthesis_sections(fallback)
    if not sections and not fallback_sections:
        return text

    direct = _limit_sentences(sections.get("direct answer", ""), 3)
    if len(direct) < 80:
        direct = _limit_sentences(fallback_sections.get("direct answer", ""), 3)

    facts = _fact_candidates(sections.get("key facts", ""))
    facts.extend(
        fact
        for fact in _fact_candidates(
            fallback_sections.get("key facts", ""), strict=True
        )
        if re.sub(r"\W+", "", fact.lower())
        not in {re.sub(r"\W+", "", item.lower()) for item in facts}
    )
    facts = facts[:6]

    lines: list[str] = []
    if direct:
        lines.extend(["Direct answer:", direct, ""])
    if facts:
        lines.append("Key facts:")
        lines.extend(f"- {fact}" for fact in facts)
    return "\n".join(lines).strip() or text


def _filter_unsupported_facts(text: str, context: str) -> str:
    context_years = set(re.findall(r"\b(?:19|20)\d{2}\b", context))
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            fact = line[2:].strip()
            fact_years = set(re.findall(r"\b(?:19|20)\d{2}\b", fact))
            if _unsupported_entities(fact, context) or (fact_years - context_years):
                continue
        kept.append(line)
    return "\n".join(kept).strip()


def _loses_concrete_facts(text: str, draft: str) -> bool:
    """Reject a rewrite that drops the key year from the verified answer."""
    direct = _synthesis_sections(draft).get("direct answer", draft)
    draft_years = set(re.findall(r"\b(?:19|20)\d{2}\b", direct))
    text_years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
    return bool(draft_years - text_years)


def synthesize_research(
    query: str, sources: list[dict[str, Any]]
) -> tuple[str, str]:
    """Answer the query from source text; return (content, method)."""
    ranked = _rank_sources(query, sources, limit=4)
    context: list[str] = []
    for index, source in enumerate(ranked, start=1):
        title = str(source.get("title", "Untitled")).strip()
        url = str(source.get("url", "")).strip()
        text = str(source.get("text", "") or source.get("snippet", "") or "").strip()
        if not text:
            continue
        compact = re.sub(r"\s+", " ", text)[:1400]
        context.append(f"[{index}] {title}\nURL: {url}\n{compact}")
    context_text = "\n\n".join(context)

    extractive = _extractive_summary(query, ranked)

    # weather: interpreted extractive is reliable and readable
    if _is_weather_query(query) and extractive:
        return extractive, "extractive"

    if not context:
        # no retrieved sources: try best-effort answer from model, else simple notice
        try:
            response = _client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant. Answer clearly and directly in plain text. "
                            "Use this structure:\nDirect answer: 1-3 sentences answering the question.\n\n"
                            "Key facts:\n- 3-6 concise bullet points.\n\nDetails:\n1-2 short paragraphs.\n"
                            "If you are not sure about specific up-to-date details, say so briefly without inventing."
                        ),
                    },
                    {"role": "user", "content": f"Question: {query}\n\nProvide a clear, informative answer."},
                ],
                options={"temperature": 0.3, "num_predict": 350},
            )
            raw = response.message.content if hasattr(response, "message") else response["message"]["content"]
            text = _format_synthesis(_clean_synthesis(str(raw)))
            if len(text) >= 40:
                return text, "llm"
        except Exception as exc:
            logging.warning("No-source synthesis failed: %s", exc)
        if extractive:
            return extractive, "extractive"
        return (
            "Direct answer:\n"
            f'I could not retrieve enough information to fully answer "{query}".\n\n'
            "Key facts:\n- Web sources were not available or returned no usable content.\n\n"
            "Details:\nTry again in a moment or rephrase the question for a more specific topic."
        ), "fallback"

    user_prompt = (
        f"Question: {query}\n\n"
        "Verified draft (extracted from the best sources):\n"
        f"{extractive or 'No reliable draft could be extracted.'}\n\n"
        "Source extracts:\n\n" + "\n\n".join(context) + "\n\n"
        "Rewrite the verified draft into a clear, natural report. Keep every concrete "
        "fact (dates, names, numbers, places, platforms). Do not add facts that are "
        "not in the draft or source extracts. Structure it as: Direct answer / Key facts."
    )
    try:
        response = _client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _RESEARCH_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0.2, "num_predict": 350},
        )
        raw = response.message.content if hasattr(response, "message") else response["message"]["content"]
        text = _format_synthesis(_clean_synthesis(str(raw)), extractive)
        text = _filter_unsupported_facts(text, context_text)
        direct = _synthesis_sections(text).get("direct answer", "")
        if _unsupported_entities(direct, context_text):
            text = extractive
        missing = _unsupported_numbers(text, context_text)
        sourcey = bool(
            re.search(
                r"\b(retrieved|snippet|web page|according to the|verified draft)\b",
                text,
                re.IGNORECASE,
            )
        )
        lost_facts = _loses_concrete_facts(text, extractive)
        bad = not text or len(text) < 40 or bool(missing) or lost_facts
        if not bad and not (sourcey and len(text) < 120):
            return text, "llm"
        logging.warning(
            "Research synthesis unusable/missing=%s/lost_facts=%s; using fallback",
            missing[:3],
            lost_facts,
        )
    except Exception as exc:
        logging.warning("Research synthesis failed; using fallback: %s", exc)

    if extractive:
        return extractive, "extractive"
    # last resort: readable summary from snippets
    parts = []
    for s in ranked[:4]:
        sn = _clean_fragment(str(s.get("snippet") or s.get("title") or ""))
        if sn and len(sn) > 20:
            parts.append(_shorten(sn, 220))
    parts = _dedupe_keep(parts)
    if parts:
        lines = ["Direct answer:", parts[0], "", "Key facts:"]
        for p in parts[:5]:
            lines.extend([f"- {p}", ""])
        lines.extend(["Details:", "Summary based on available search results."])
        return "\n".join(lines).strip(), "extractive"
    return (
        "Direct answer:\n"
        f'Not enough clear information was available to fully answer "{query}".\n\n'
        "Key facts:\n- Retrieved results were too limited to extract reliable details.\n\n"
        "Details:\nTry a more specific question."
    ), "fallback"

_NUMBER_FACT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:\u00b0c|\u00b0f|%|km/h|mm|cm|m/s|mph|kn|hours?|hrs?|days?|am|pm)"
    r"(?=\s|$|[.,;:)])"
    r"|\b\d{1,2}:\d{2}\b"
    r"|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


def _normalized_fact(value: str) -> str:
    return re.sub(r"\s+", "", value.lower()).replace(",", ".")


def _unsupported_numbers(text: str, context: str) -> list[str]:
    """Find numeric claims that are not present in the retrieved source text."""
    haystack = _normalized_fact(context)
    missing: list[str] = []
    for match in _NUMBER_FACT_RE.finditer(text):
        token = _normalized_fact(match.group(0))
        if token and token not in haystack:
            missing.append(match.group(0))
    return missing

