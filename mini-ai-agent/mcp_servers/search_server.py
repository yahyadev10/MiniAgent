import html as html_lib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from html.parser import HTMLParser

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36 "
    "MiniAIAgent/1.0"
)

mcp = FastMCP(
    "search-server",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8003")),
    # Containers are reached through Docker service names, not localhost.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside"}
_RESULT_LINK_RE = re.compile(
    r"<a\b(?=[^>]*class=['\"]result-link['\"])[^>]*"
    r"href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_RESULT_SNIPPET_RE = re.compile(
    r"<td[^>]*class=['\"]result-snippet['\"][^>]*>(.*?)</td>",
    re.IGNORECASE | re.DOTALL,
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def _fetch(
    url: str,
    timeout: int = 15,
    max_bytes: int = 800_000,
    attempts: int = 2,
    accept: str = "text/html,application/json;q=0.9,*/*;q=0.8",
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
                "Accept": accept,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(max_bytes)
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, "replace")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(0.8 * attempt)
    raise last_error or RuntimeError(f"Unable to fetch {url}")


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _decode_ddg_link(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlsplit(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
        return target
    return href


def _clean_markdown(value: str) -> str:
    """Turn Jina's markdown rendering of a result page into plain text."""
    text = value or ""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"[#>*_`]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_ROMAN_NUMBERS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}


def _tokens(value: str) -> list[str]:
    text = html_lib.unescape(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [token for token in text.split() if token]


def _title_token_points(query_token: str, title_tokens: list[str]) -> int:
    if query_token in title_tokens:
        return 5
    if query_token.isdigit():
        number = int(query_token)
        if any(_ROMAN_NUMBERS.get(token) == number for token in title_tokens):
            return 5
    if len(query_token) >= 2:
        width = len(query_token)
        for index in range(len(title_tokens) - width + 1):
            initials = "".join(token[0] for token in title_tokens[index : index + width])
            if initials == query_token:
                return 6
    for token in title_tokens:
        if len(token) >= 4 and SequenceMatcher(None, query_token, token).ratio() >= 0.8:
            return 2
    return 0


def _relevance_score(query: str, item: dict[str, str]) -> int:
    """Estimate whether a result actually talks about the requested topic."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0
    title_tokens = _tokens(item.get("title", ""))
    url_tokens = _tokens(item.get("url", ""))
    snippet_tokens = _tokens(item.get("snippet", ""))

    score = 0
    title_hits = 0
    for token in query_tokens:
        points = _title_token_points(token, title_tokens)
        if points:
            score += points
            title_hits += 1
        elif token in url_tokens:
            score += 2
        elif token in snippet_tokens:
            score += 1
        else:
            score -= 1

    if " ".join(query_tokens) in " ".join(title_tokens):
        score += 6
    if title_hits == 0:
        score -= 4
    # A number in the query (GTA 5, Windows 11...) should appear as a digit or
    # roman numeral in the title; otherwise it is probably the wrong entry.
    query_numbers = {int(token) for token in query_tokens if token.isdigit()}
    title_numbers = {
        _ROMAN_NUMBERS[token]
        for token in title_tokens
        if token in _ROMAN_NUMBERS
    }
    if query_numbers:
        if not title_numbers and not any(token.isdigit() for token in title_tokens):
            score -= 3
        elif title_numbers and not (query_numbers & title_numbers):
            score -= 6
    return score


def _rank_results(
    query: str,
    results: list[dict[str, str]],
    max_results: int,
    strict: bool = False,
) -> list[dict[str, str]]:
    scored: list[tuple[int, int, dict[str, str]]] = []
    for order, item in enumerate(results):
        score = _relevance_score(query, item)
        if strict and score < 8:
            continue
        if not strict and score < 0:
            continue
        scored.append((score, order, item))

    if not scored and not strict:
        scored = [(0, order, item) for order, item in enumerate(results[:2])]

    scored.sort(key=lambda row: (-row[0], row[1]))
    ranked: list[dict[str, str]] = []
    for score, _, item in scored[:max_results]:
        enriched = dict(item)
        enriched["relevance"] = score
        ranked.append(enriched)
    return ranked


def _search_duckduckgo(query: str, max_results: int) -> list[dict[str, str]]:
    url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
    raw = _fetch(url, timeout=20, attempts=2)
    links = _RESULT_LINK_RE.findall(raw)
    snippets = _RESULT_SNIPPET_RE.findall(raw)

    results: list[dict[str, str]] = []
    for index, (href, title_html) in enumerate(links[:max_results]):
        title = _clean_html(title_html)
        target = _decode_ddg_link(href)
        if not title or not target.startswith(("http://", "https://")):
            continue
        results.append(
            {
                "title": title,
                "url": target,
                "snippet": _clean_html(snippets[index]) if index < len(snippets) else "",
            }
        )
    return results


_JINA_HEADING_RE = re.compile(
    r"^##\s+\[([^\]]+)\]\(([^)]+)\)\s*$",
    re.MULTILINE,
)


def _search_jina_duckduckgo(query: str, max_results: int) -> list[dict[str, str]]:
    """Use Jina Reader to fetch DuckDuckGo HTML when direct access is blocked."""
    target = "http://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    url = "https://r.jina.ai/" + target
    raw = _fetch(
        url,
        timeout=45,
        max_bytes=900_000,
        attempts=2,
        accept="text/plain",
    )
    headings = list(_JINA_HEADING_RE.finditer(raw))
    results: list[dict[str, str]] = []
    for index, match in enumerate(headings[: max_results * 2]):
        title = _clean_markdown(match.group(1))
        link = _decode_ddg_link(match.group(2))
        if not title or not link.startswith(("http://", "https://")):
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(raw)
        block = raw[match.end() : end]
        snippet = ""
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("!["):
                continue
            cleaned = _clean_markdown(line)
            if not cleaned:
                continue
            if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}(/\S*)?", cleaned, re.I):
                continue
            if len(cleaned) > len(snippet):
                snippet = cleaned
        if any(item["url"] == link for item in results):
            continue
        results.append({"title": title, "url": link, "snippet": snippet[:500]})
        if len(results) >= max_results:
            break
    return results


def _search_bing(query: str, max_results: int) -> list[dict[str, str]]:
    """Bing's RSS endpoint is a reliable no-key fallback."""
    params = {"q": query, "format": "rss", "mkt": "en-US"}
    url = "https://www.bing.com/search?" + urllib.parse.urlencode(params)
    raw = _fetch(
        url,
        timeout=25,
        attempts=2,
        accept="application/rss+xml,text/xml;q=0.9,*/*;q=0.8",
    )
    root = ET.fromstring(raw.encode("utf-8"))
    results: list[dict[str, str]] = []
    for item in root.findall("./channel/item")[:max_results]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = _clean_html(item.findtext("description") or "")
        if title and link.startswith(("http://", "https://")):
            results.append(
                {"title": title, "url": link, "snippet": description[:500]}
            )
    return results


def _wikipedia_search_once(query: str, max_results: int) -> list[dict[str, str]]:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "utf8": "1",
        "srlimit": str(max_results),
    }
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    payload = json.loads(_fetch(url))
    results: list[dict[str, str]] = []
    for item in payload.get("query", {}).get("search", [])[:max_results]:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        results.append(
            {
                "title": title,
                "url": "https://en.wikipedia.org/wiki/"
                + urllib.parse.quote(title.replace(" ", "_")),
                "snippet": _clean_html(str(item.get("snippet", ""))),
            }
        )
    return results


def _wiki_query_variants(query: str) -> list[str]:
    """Try a compact acronym+number query when the full sentence is noisy."""
    variants = [query]
    compact = re.search(r"\b([A-Za-z]{2,6})\s*[- ]?(\d{1,2})\b", query)
    if compact:
        short = f"{compact.group(1)} {compact.group(2)}"
        if short.lower() not in {variant.lower() for variant in variants}:
            variants.append(short)
    cleaned = re.sub(r"\([^)]*\)", " ", query)
    cleaned = re.sub(
        r"\b(report|rapport|summary|resume|about|sur|concernant|the|a|an|de|du|des)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned.lower() not in {variant.lower() for variant in variants}:
        variants.append(cleaned)
    return variants[:3]


def _search_wikipedia(query: str, max_results: int) -> list[dict[str, str]]:
    """Search Wikipedia with variants, then keep only on-topic entries."""
    collected: list[dict[str, str]] = []
    seen: set[str] = set()
    for variant in _wiki_query_variants(query):
        try:
            items = _wikipedia_search_once(variant, max_results)
        except Exception:
            continue
        for item in items:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            collected.append(item)
    return _rank_results(query, collected, max_results, strict=True)


def _page_text(url: str, limit: int = 2200) -> str:
    try:
        raw = _fetch(url, timeout=12, max_bytes=1_200_000)
        parser = _TextExtractor()
        parser.feed(raw)
        text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
        return text[:limit]
    except Exception:
        return ""


_QUERY_ALIASES = {
    "gta 5": "Grand Theft Auto V",
    "gta v": "Grand Theft Auto V",
    "gtav": "Grand Theft Auto V",
    "grand theft auto 5": "Grand Theft Auto V",
}


def _resolve_query(query: str) -> str:
    """Expand short/ambiguous entity queries with Wikipedia's canonical title."""
    words = query.split()
    if not words or len(words) > 6:
        return query
    normalized = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    if normalized in _QUERY_ALIASES:
        return _QUERY_ALIASES[normalized]
    if re.search(
        r"\b(weather|forecast|news|price|stock|who|what|when|where|why|how)\b",
        query,
        re.IGNORECASE,
    ):
        return query
    if len(words) > 2 and not re.search(r"\b[A-Z]{2,}\b|\d", query):
        return query

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": "3",
        "namespace": "0",
        "format": "json",
    }
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        payload = json.loads(_fetch(url, timeout=10, accept="application/json"))
        for item in payload.get("query", {}).get("search", []):
            title = str(item.get("title", "")).strip()
            candidate = {"title": title, "url": "", "snippet": ""}
            if title and _relevance_score(query, candidate) >= 8:
                return title
    except Exception:
        pass
    return query


def _wikipedia_extract(url: str, limit: int = 3200) -> str:
    """Use the Wikipedia API to get clean intro text instead of HTML chrome."""
    title = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "exintro": "1",
        "redirects": "1",
        "titles": title,
        "format": "json",
        "utf8": "1",
    }
    api_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        payload = json.loads(
            _fetch(api_url, timeout=15, accept="application/json")
        )
        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = str(page.get("extract", "") or "").strip()
            if extract:
                extract = re.sub(r"\[[^\]]{1,40}\]", "", extract)
                extract = re.sub(r"\s+", " ", extract).strip()
                return extract[:limit]
    except Exception:
        pass
    return _page_text(url, limit)


def _add_page_text(results: list[dict[str, str]], limit: int = 8) -> None:
    limit = min(limit, len(results))

    def fetch_text(item: dict[str, str]) -> str:
        if "wikipedia.org/wiki/" in item.get("url", ""):
            return _wikipedia_extract(item["url"])
        return _page_text(item["url"])

    with ThreadPoolExecutor(max_workers=max(1, limit)) as executor:
        texts = list(executor.map(fetch_text, results[:limit]))
    for item, text in zip(results[:limit], texts):
        item["text"] = text
        if text and (
            not item.get("snippet") or "wikipedia.org/wiki/" in item.get("url", "")
        ):
            item["snippet"] = text[:500]


_WEATHER_RE = re.compile(
    r"\b(weather|forecast|meteo|météo|temperature|temperatures|rain|snow)\b",
    re.IGNORECASE,
)
_WEATHER_STOPWORDS = {
    "what", "whats", "what's", "is", "are", "the", "a", "an", "like", "today",
    "tomorrow", "tonight", "current", "currently", "now", "in", "for", "at",
    "of", "please", "tell", "me", "how", "will", "be", "this", "week",
    "weekend", "weather", "forecast", "meteo", "météo", "temperature",
    "temperatures", "rain", "snow", "quel", "quels", "quelle", "quelles",
    "est", "sont", "actuel", "actuelle", "actuels", "actuelles", "a", "en",
    "la", "le", "les", "l", "un", "une", "de", "du", "des",
    "au", "aux", "dans", "sur", "pour", "fait", "faire", "il", "y", "aujourdhui",
    "maintenant", "prevision", "previsions", "prevision", "prévisions",
}
_WMO_LABELS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _weather_location(query: str) -> str:
    words = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    kept = [
        word for word in words
        if word.lower() not in _WEATHER_STOPWORDS and len(word) > 1
    ]
    return " ".join(kept).strip()


def _number(value: object, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "?"


def _search_weather(query: str) -> list[dict[str, str]]:
    """Use Open-Meteo for live weather instead of scraping forecast pages."""
    if not _WEATHER_RE.search(query):
        return []
    location = _weather_location(query)
    if not location:
        return []
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": location, "count": 8, "language": "en", "format": "json"}
    )
    try:
        geo = json.loads(
            _fetch(geo_url, timeout=15, attempts=2, accept="application/json")
        )
        candidates = geo.get("results") or []
        wanted = location.casefold().strip()
        place = next(
            (item for item in candidates if str(item.get("name", "")).casefold() == wanted),
            None,
        )
        if place is None:
            place = next(
                (item for item in candidates if wanted in str(item.get("name", "")).casefold()),
                None,
            )
        if place is None:
            place = candidates[0] if candidates else None
    except Exception as exc:
        print(f"[WEATHER] geocoding failed for {location!r}: {exc}", flush=True)
        return []
    if not place:
        return []

    label = ", ".join(
        str(part) for part in
        (place.get("name"), place.get("admin1"), place.get("country")) if part
    )
    params = {
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,weather_code,wind_speed_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        ),
        "timezone": "auto",
        "forecast_days": 3,
    }
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        params
    )
    try:
        data = json.loads(
            _fetch(forecast_url, timeout=15, attempts=2, accept="application/json")
        )
    except Exception as exc:
        print(f"[WEATHER] forecast failed for {label!r}: {exc}", flush=True)
        return []

    current = data.get("current") or {}
    units = data.get("current_units") or {}
    daily = data.get("daily") or {}
    temp_unit = units.get("temperature_2m", "°C")
    wind_unit = units.get("wind_speed_10m", "km/h")
    code = current.get("weather_code")
    condition = _WMO_LABELS.get(int(code), "unknown conditions") if code is not None else ""
    parts = [
        f"Current conditions in {label}: {_number(current.get('temperature_2m'))}"
        f"{temp_unit}, feels like {_number(current.get('apparent_temperature'))}"
        f"{temp_unit}, {condition}, humidity "
        f"{_number(current.get('relative_humidity_2m'), 0)}%, wind "
        f"{_number(current.get('wind_speed_10m'))} {wind_unit}, precipitation "
        f"{_number(current.get('precipitation'))} mm."
    ]
    dates = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    chances = daily.get("precipitation_probability_max") or []
    for index, date in enumerate(dates[:3]):
        high = highs[index] if index < len(highs) else None
        low = lows[index] if index < len(lows) else None
        chance = chances[index] if index < len(chances) else None
        parts.append(
            f"{date}: {_number(low)}{temp_unit} to {_number(high)}{temp_unit}, "
            f"{_number(chance, 0)}% chance of precipitation."
        )
    daily_items = []
    for index, date in enumerate(dates[:3]):
        daily_items.append(
            {
                "date": date,
                "low": lows[index] if index < len(lows) else None,
                "high": highs[index] if index < len(highs) else None,
                "chance": chances[index] if index < len(chances) else None,
            }
        )
    return [
        {
            "title": f"Live weather forecast for {label}",
            "url": "https://open-meteo.com/",
            "snippet": " ".join(parts),
            "weather": {
                "location": label,
                "current": {
                    "temperature": current.get("temperature_2m"),
                    "apparent": current.get("apparent_temperature"),
                    "humidity": current.get("relative_humidity_2m"),
                    "wind": current.get("wind_speed_10m"),
                    "precipitation": current.get("precipitation"),
                    "condition": condition,
                    "temperature_unit": temp_unit,
                    "wind_unit": wind_unit,
                },
                "daily": daily_items,
            },
        }
    ]


@mcp.tool()
def web_search(
    query: str,
    max_results: int = 5,
    fetch_pages: bool = True,
) -> str:
    """Search the public web and return titles, URLs, snippets and page extracts."""
    query = (query or "").strip()[:300]
    max_results = max(1, min(int(max_results), 8))
    if not query:
        return json.dumps(
            {"status": "error", "error": "A search query is required."},
            ensure_ascii=False,
        )

    search_query = _resolve_query(query)
    results: list[dict[str, str]] = []
    engine = "none"
    errors: list[str] = []
    weather_results = _search_weather(query)
    if weather_results:
        results = weather_results[:max_results]
        engine = "open-meteo"
    else:
        engines = (
            ("duckduckgo-lite", _search_duckduckgo),
            ("jina-duckduckgo", _search_jina_duckduckgo),
            ("bing-rss", _search_bing),
            ("wikipedia", _search_wikipedia),
        )
        for name, search in engines:
            try:
                raw_results = search(search_query, max_results)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                print(f"[SEARCH] {name} failed: {exc}", flush=True)
                raw_results = []
            results = _rank_results(
                search_query,
                raw_results,
                max_results,
                strict=(name == "wikipedia"),
            )
            if results:
                engine = name
                break

    if not results:
        payload = {
            "status": "error",
            "query": query,
            "resolved_query": search_query,
            "error": "Search failed: " + "; ".join(errors),
        }
        print(f"[SEARCH ERROR] {payload}", flush=True)
        return json.dumps(payload, ensure_ascii=False)

    if fetch_pages and engine != "open-meteo":
        _add_page_text(results)

    payload = {
        "status": "ok",
        "engine": engine,
        "query": query,
        "resolved_query": search_query,
        "count": len(results),
        "results": results,
    }
    print(
        f"[SEARCH] {engine} query={query!r} resolved={search_query!r} results={len(results)}",
        flush=True,
    )
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
