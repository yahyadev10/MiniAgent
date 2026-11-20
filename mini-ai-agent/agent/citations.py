from typing import Any

from agent.llm import _rank_sources


def build_citations(query: str, sources: list[dict[str, Any]], limit: int = 6) -> list[dict[str, str]]:
    """Return ranked, deduplicated sources that can be rendered as footnotes."""
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in _rank_sources(query, sources, limit=limit + 4):
        url = str(source.get("url", "") or "").strip()
        title = str(source.get("title", "") or "Untitled").strip()
        key = url or title
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        citations.append({"title": title, "url": url})
        if len(citations) >= limit:
            break
    return citations
