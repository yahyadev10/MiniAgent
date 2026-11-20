import asyncio
import json
import logging
import os
import time
from functools import wraps
from typing import Any, Awaitable, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agent.citations import build_citations
from agent.llm import classify_request, synthesize_research, topic_from_message
from agent.state import AgentState

EMAIL_MCP_URL = os.getenv("EMAIL_MCP_URL", "http://email-mcp:8001/mcp")
REPORT_MCP_URL = os.getenv("REPORT_MCP_URL", "http://report-mcp:8002/mcp")
SEARCH_MCP_URL = os.getenv("SEARCH_MCP_URL", "http://search-mcp:8003/mcp")


def _timed(
    name: str,
) -> Callable[[Callable[..., Awaitable[dict]]], Callable[..., Awaitable[dict]]]:
    """Record a lightweight execution step (node, status, duration) for the UI."""

    def decorator(
        fn: Callable[..., Awaitable[dict]],
    ) -> Callable[..., Awaitable[dict]]:
        @wraps(fn)
        async def wrapper(state: AgentState) -> dict[str, Any]:
            started = time.perf_counter()
            try:
                update = await fn(state)
            except Exception:
                elapsed = int((time.perf_counter() - started) * 1000)
                logging.exception("Node '%s' failed after %d ms", name, elapsed)
                raise
            elapsed = int((time.perf_counter() - started) * 1000)
            result = dict(update or {})
            result["steps"] = [{"node": name, "status": "ok", "ms": elapsed}]
            return result

        return wrapper

    return decorator


async def _call_mcp_tool(
    url: str,
    tool_name: str,
    arguments: dict[str, Any],
    attempts: int = 3,
) -> str:
    """Call a tool on a remote MCP server using the MCP protocol."""
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            async with streamablehttp_client(url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)

                    if result.isError:
                        raise RuntimeError(
                            f"MCP tool '{tool_name}' returned an error: {result.content}"
                        )

                    texts = [getattr(block, "text", "") for block in result.content]
                    return "\n".join(text for text in texts if text) or str(result.content)
        except Exception as exc:
            last_error = exc
            logging.warning(
                "MCP call '%s' attempt %d/%d failed: %s",
                tool_name,
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                await asyncio.sleep(1.5 * attempt)

    raise RuntimeError(f"Unable to call MCP tool '{tool_name}' at {url}: {last_error}")


def _parse_payload(text: str) -> dict[str, Any] | None:
    """MCP tools return JSON as text; parse it when possible."""
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _format_report(payload: dict[str, Any] | None, raw: str) -> str:
    if not payload or payload.get("status") != "generated":
        return raw

    files = payload.get("files", [])
    names = ", ".join(str(item.get("filename", "?")) for item in files)
    summary = payload.get("summary", {})
    sources = payload.get("sources", [])
    rows = int(summary.get("rows", 0) or 0)
    columns = int(summary.get("columns", 0) or 0)
    data_note = f" ({rows} rows, {columns} columns)" if rows or columns else ""
    source_note = f" with {len(sources)} web sources" if sources else ""
    return f"Report generated: {names}{data_note}{source_note}."


def _format_email(payload: dict[str, Any] | None, raw: str) -> str:
    if not payload:
        return raw

    status = payload.get("status")
    if status == "sent":
        return (
            f"Email sent to {payload.get('to')} "
            f"with subject '{payload.get('subject')}'."
        )
    if status == "saved":
        return (
            "SMTP is not configured, so the email was saved as "
            f"{payload.get('file')} (ready to send)."
        )
    return f"Email failed: {payload.get('error', 'unknown error')}"


@_timed("classify")
async def classify_node(state: AgentState) -> dict[str, Any]:
    """Use explicit form fields when provided, otherwise ask the LLM."""
    action_hint = (state.get("action_hint") or "auto").strip().lower()
    message = (state.get("message") or "").strip()

    if action_hint in {"email", "report", "both"}:
        action = action_hint
        data: dict[str, Any] = {}
        logging.info("Structured request -> %s (LLM skipped)", action)
    else:
        result = classify_request(message)
        action = result["action"]
        data = result["data"]
        logging.info("Classified %r -> %s", message, action)

    email_args = {
        "to": str(state.get("to") or data.get("to") or "john@example.com"),
        "subject": str(
            state.get("subject")
            or data.get("subject")
            or "Message from Mini AI Agent"
        ),
        "body": str(
            state.get("body")
            or data.get("body")
            or message
            or "Hello, this is a message from the Mini AI Agent."
        ),
    }
    report_args = {
        "title": str(
            state.get("title") or data.get("title") or "Mini AI Agent Report"
        ),
        "content": str(
            state.get("content")
            or data.get("content")
            or message
            or "Report generated by the Mini AI Agent."
        ),
        "data": state.get("data", ""),
        "source_filename": state.get("filename", ""),
        "sources": [],
    }
    search_query = str(
        state.get("title") or data.get("title") or topic_from_message(message)
    ).strip()

    return {
        "action": action,
        "email_args": email_args,
        "report_args": report_args,
        "search_query": search_query,
    }


@_timed("email")
async def email_node(state: AgentState) -> dict[str, Any]:
    """Branch that sends a real email (or saves a .eml file) via MCP."""
    attachments = [
        str(item["filename"])
        for item in state.get("artifacts", [])
        if item.get("kind") in {"pdf", "html"} and item.get("filename")
    ]
    arguments = dict(state["email_args"])
    arguments["attachments"] = attachments

    result = await _call_mcp_tool(EMAIL_MCP_URL, "send_email", arguments)
    payload = _parse_payload(result)

    artifacts: list[dict[str, Any]] = []
    if payload and payload.get("status") == "saved" and payload.get("file"):
        artifacts.append(
            {
                "kind": "eml",
                "filename": str(payload["file"]),
                "size": int(payload.get("size", 0)),
            }
        )

    return {
        "results": [f"[email] {_format_email(payload, result)}"],
        "artifacts": artifacts,
    }


def _needs_research(state: AgentState) -> bool:
    """Research for report/both when no dataset is provided (web-grounded answer)."""
    if state.get("action") not in {"report", "both"}:
        return False
    if (state.get("data") or "").strip():
        return False
    # If user explicitly provided structured report content different from the
    # original request, treat it as the report body; otherwise research.
    content = (state.get("content") or "").strip()
    message = (state.get("message") or "").strip()
    if content and message and content != message and len(content) > 40:
        return False
    return bool((state.get("search_query") or message or "").strip())


@_timed("research")
async def research_node(state: AgentState) -> dict[str, Any]:
    """Collect public web sources to feed a report (best-effort)."""
    if not _needs_research(state):
        return {}

    query = str(
        state.get("search_query") or topic_from_message(state.get("message", "")) or state.get("message", "")
    ).strip()
    try:
        result = await _call_mcp_tool(
            SEARCH_MCP_URL,
            "web_search",
            {"query": query, "max_results": 8, "fetch_pages": True},
        )
    except Exception as exc:
        logging.warning("Web research failed for %r: %s", query, exc)
        return {
            "search_query": query,
            "results": [f"[research] Web search unavailable: {exc}"],
        }

    payload = _parse_payload(result)
    items = payload.get("results", []) if payload else []
    if payload is None or payload.get("status") != "ok" or not items:
        return {
            "search_query": query,
            "results": [f"[research] No web results found for '{query}'."],
        }

    sources: list[dict[str, str]] = []
    lines = [f'Web research summary for: "{query}".', ""]
    for index, item in enumerate(items, start=1):
        title = str(item.get("title", "Untitled")).strip()
        url = str(item.get("url", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        text = str(item.get("text", "") or "").strip()
        if not url:
            continue
        source = {"title": title, "url": url, "snippet": snippet, "text": text}
        if isinstance(item.get("weather"), dict):
            source["weather"] = item["weather"]
        sources.append(source)
        lines.append(f"{index}. {title}")
        if snippet:
            lines.append(snippet)
        lines.append("")

    if not sources:
        return {
            "search_query": query,
            "results": [f"[research] No usable web sources found for '{query}'."],
        }

    content = "\n".join(lines).strip()[:20_000]
    report_args = {
        **state["report_args"],
        "content": content,
        "sources": sources,
    }
    return {
        "search_query": query,
        "report_args": report_args,
        "sources": sources,
        "results": [
            f"[research] {len(sources)} web sources found for '{query}' "
            f"via {payload.get('engine', 'web search')}."
        ],
    }


@_timed("synthesize")
async def synthesize_node(state: AgentState) -> dict[str, Any]:
    """Turn retrieved sources (or the question) into an actual answer for the report."""
    if state.get("action") not in {"report", "both"} or (state.get("data") or "").strip():
        return {}
    # respect explicit, non-trivial user-provided content
    content_in = (state.get("content") or "").strip()
    message = (state.get("message") or "").strip()
    if content_in and message and content_in != message and len(content_in) > 40 and not state.get("sources"):
        return {}

    query = str(
        state.get("search_query")
        or state.get("report_args", {}).get("title")
        or topic_from_message(message)
        or message
    ).strip()
    sources = state.get("sources") or []

    content, method = await asyncio.to_thread(synthesize_research, query, sources)
    if not content.strip():
        content = (
            "Direct answer:\n"
            f'I could not gather enough information to fully answer "{query}".\n\n'
            "Key facts:\n"
            "- No reliable details were retrieved for this request.\n\n"
            "Details:\n"
            "Try rephrasing the question or providing a dataset for a data report."
        )
        method = "fallback"

    citations = build_citations(query, sources)
    report_args = {
        **state["report_args"],
        "title": state.get("report_args", {}).get("title") or query or "Report",
        "content": content,
        "sources": sources,
        "citations": citations,
    }
    label = "local model" if method == "llm" else ("extracted" if sources else "best effort")
    return {
        "citations": citations,
        "report_args": report_args,
        "results": [
            f"[synthesize] Answer prepared for '{query}' ({label}, {len(sources)} sources)."
        ],
    }


@_timed("report")
async def report_node(state: AgentState) -> dict[str, Any]:
    """Branch that generates real PDF + HTML files via MCP."""
    result = await _call_mcp_tool(
        REPORT_MCP_URL,
        "generate_report",
        state["report_args"],
    )
    payload = _parse_payload(result)

    artifacts: list[dict[str, Any]] = []
    if payload and payload.get("status") == "generated":
        for item in payload.get("files", []):
            filename = item.get("filename")
            if filename:
                artifacts.append(
                    {
                        "kind": str(item.get("kind", "file")),
                        "filename": str(filename),
                        "size": int(item.get("size", 0)),
                    }
                )

    return {
        "results": [f"[report] {_format_report(payload, result)}"],
        "artifacts": artifacts,
    }


@_timed("unsupported")
async def unsupported_node(state: AgentState) -> dict[str, Any]:
    """Branch used when the request does not match a known tool."""
    return {
        "results": [
            "[unsupported] No email or report action was detected. "
            "Mention 'email' or 'report' in your request."
        ]
    }


@_timed("finalize")
async def finalize_node(state: AgentState) -> dict[str, Any]:
    """Join all tool outputs into a single final answer."""
    return {"final": "\n".join(state.get("results", []))}
