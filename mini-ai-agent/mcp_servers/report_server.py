import csv
import html
import io
import json
import os
import re
import statistics
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP(
    "report-server",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8002")),
    # Containers are reached through Docker service names, not localhost.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


class _Drawing(Flowable):
    """Wrap a ReportLab drawing so it can be placed inside a Platypus story."""

    def __init__(self, drawing: Drawing, width: float, height: float) -> None:
        super().__init__()
        self.drawing = drawing
        self.width = width
        self.height = height

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        self.drawing.drawOn(self.canv, 0, 0)


_BOILERPLATE_RE = re.compile(
    r"(ad free|remove ads|book a timeslot|join us for a video call|"
    r"download (?:the|our) .*?app|get the .*?app|location search|darkmode|"
    r"cookie(?:s| policy)?|privacy(?: policy)?|all rights reserved|"
    r"subscribe|sign in|log in|advertisement|sponsored|follow us|share this|"
    r"read on|manage (?:your )?preferences|terms of service)",
    re.IGNORECASE,
)

_PDF_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u2022": "-",
        "\u00a0": " ",
        "\u20ac": "EUR",
    }
)


def _clean_text(value: object, limit: int = 20_000) -> str:
    """Normalize user/web text and drop the most common encoding noise."""
    text = str(value or "")
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_PDF_TRANSLATION)
    text = "".join(
        char
        for char in text
        if char in "\n\t"
        or unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
    )
    text = text.replace("\ufffd", "")
    text = re.sub(r"(?<=\w)\?{2,}(?=\w)", "", text)
    text = re.sub(r"\?{2,}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([!?.,;:])\1{2,}", r"\1\1", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()[:limit]


def _pdf_text(value: object) -> str:
    """Make cleaned text safe for the built-in PDF fonts (Latin-1)."""
    text = _clean_text(value).translate(_PDF_TRANSLATION)
    return text.encode("latin-1", "replace").decode("latin-1")


def _pdf_markup(value: object) -> str:
    """Escape cleaned text before passing it to a ReportLab Paragraph."""
    return xml_escape(_pdf_text(value))


def _split_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text)
        if part.strip()
    ]


def _is_boilerplate(text: str) -> bool:
    if _BOILERPLATE_RE.search(text):
        return True
    words = re.findall(r"[A-Za-z0-9\u00c0-\u00ff]+", text)
    if not words or len(text) < 3:
        return True
    noisy = len(re.findall(r"[^\w\s.,;:!?'\"()%+\-/]", text))
    return noisy > max(6, len(text) * 0.2)


def _clean_paragraphs(content: str, limit: int = 12) -> list[str]:
    """Turn a raw request/research dump into a short list of clean paragraphs."""
    text = _clean_text(content)
    paragraphs: list[str] = []
    seen: set[str] = set()

    for block in re.split(r"\n\s*\n", text):
        sentences: list[str] = []

        def flush() -> None:
            if sentences:
                paragraphs.append(" ".join(sentences))
                sentences.clear()

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.match(r"^source\s*:", line, re.IGNORECASE):
                continue
            line = re.sub(r"^extract\s*:\s*", "", line, flags=re.IGNORECASE)
            line = re.sub(r"^\d+[.)]\s*", "", line)
            line = re.sub(r"https?://\S+", "", line, flags=re.IGNORECASE).strip()
            line = re.sub(r"\s{2,}", " ", line)
            if not line:
                continue

            heading = re.match(
                r"^(Direct answer|Key facts|Details):\s*(.*)$", line, re.IGNORECASE
            )
            if heading:
                flush()
                name = heading.group(1).title()
                rest = heading.group(2).strip()
                paragraphs.append(f"{name}: {rest}" if rest else f"{name}:")
                continue

            if line.startswith(("- ", "* ", "• ")):
                flush()
                line = line[2:].strip()
                line = re.sub(r"\[\d+\]", "", line).strip()
                if line and not _is_boilerplate(line):
                    key = re.sub(r"\W+", "", line.lower())
                    if key and key not in seen:
                        seen.add(key)
                        paragraphs.append(f"- {line}")
                continue

            for part in _split_sentences(line):
                part = part.strip(" -")
                if re.match(r"^(source|extract)\s*:", part, re.IGNORECASE):
                    continue
                if _is_boilerplate(part):
                    continue
                key = re.sub(r"\W+", "", part.lower())
                if not key or key in seen:
                    continue
                seen.add(key)
                sentences.append(part)

        flush()
        if len(paragraphs) >= limit:
            break

    return paragraphs[:limit]


def _research_paragraphs(query: str, sources: list[dict[str, str]]) -> list[str]:
    """Build a readable overview from the clean search snippets."""
    query = _clean_text(query, 200).strip(' "\'.,;:')
    paragraphs = [f'This report reviews public web sources about "{query}".']
    for item in sources:
        title = _clean_text(item.get("title", ""), 200)
        snippet = _clean_text(item.get("snippet", ""), 500)
        if title and snippet:
            paragraphs.append(f"{title}: {snippet}")
        elif title:
            paragraphs.append(title)
        elif snippet:
            paragraphs.append(snippet)
        if len(paragraphs) >= 12:
            break
    return paragraphs


def _prepare_paragraphs(
    content: str, sources: list[dict[str, str]]
) -> list[str]:
    text = _clean_text(content)
    # only replace with snippet list when content is still the raw research dump
    if sources and re.match(r"(?i)^web research summary\b", text):
        match = re.search(r"web research summary for\s*:\s*(.+)", text, re.IGNORECASE)
        query = match.group(1).splitlines()[0].strip() if match else "the topic"
        paragraphs = _clean_paragraphs(text)
        # if cleaning left almost nothing useful, fall back to snippets overview
        if len(" ".join(paragraphs)) < 80:
            return _research_paragraphs(query, sources)
        return paragraphs

    paragraphs = _clean_paragraphs(text)
    # never echo a bare short request; produce a neutral placeholder instead
    if paragraphs and len(paragraphs) == 1 and len(paragraphs[0]) < 120 and re.match(r"(?i)^(generate|create|make|write|rapport|report)\b", paragraphs[0]):
        return ["Answer could not be prepared for this request. Please try again or provide more details."]
    return paragraphs or ["Report generated by the Mini AI Agent."]


def _parse_data(data: str) -> tuple[list[str], list[list[str]]]:
    """Parse CSV/TSV or JSON into a header row and a list of rows."""
    stripped = data.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            pretty = json.dumps(json.loads(data), indent=2, ensure_ascii=False)
            lines = pretty.splitlines()[:20]
            return ["JSON"], [[line] for line in lines]
        except json.JSONDecodeError:
            pass

    if not data.strip():
        return [], []

    try:
        dialect = csv.Sniffer().sniff(data[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(data), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], []

    headers = [cell.strip() for cell in rows[0]]
    body = [[cell.strip() for cell in row] for row in rows[1:]]
    return headers, body


def _numeric_summary(
    headers: list[str], body: list[list[str]]
) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    minimum = max(1, int(len(body) * 0.5))

    for index, name in enumerate(headers):
        values: list[float] = []
        for row in body:
            if index >= len(row):
                continue
            try:
                values.append(float(row[index]))
            except (TypeError, ValueError):
                continue
        if len(values) >= minimum:
            summary.append(
                {
                    "column": name,
                    "count": len(values),
                    "missing": len(body) - len(values),
                    "mean": round(statistics.mean(values), 4),
                    "median": round(statistics.median(values), 4),
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "std": round(statistics.pstdev(values), 4),
                }
            )
    return summary


def _insights(
    headers: list[str],
    body: list[list[str]],
    summary: list[dict[str, object]],
) -> list[str]:
    if not headers:
        return [
            "No dataset supplied; this report is based on the request and any "
            "web research."
        ]

    lines = [f"{len(body)} data rows across {len(headers)} columns."]
    if summary:
        highest = max(summary, key=lambda item: float(item["mean"]))
        widest = max(
            summary,
            key=lambda item: float(item["max"]) - float(item["min"]),
        )
        lines.append(
            f"Highest average: {highest['column']} ({highest['mean']})."
        )
        lines.append(
            f"Widest range: {widest['column']} "
            f"({widest['min']} to {widest['max']})."
        )
        lines.append(
            "Numeric columns: " + ", ".join(str(item["column"]) for item in summary)
        )
    else:
        lines.append(
            "No numeric columns detected; this report is based on the request "
            "and any web research."
        )
    return lines


def _mean_chart(summary: list[dict[str, object]]) -> _Drawing | None:
    if not summary:
        return None

    items = summary[:8]
    means = [float(item["mean"]) for item in items]
    labels = [str(item["column"])[:16] for item in items]
    lowest = min(0.0, min(means))
    highest = max(0.0, max(means))
    if highest == lowest:
        highest = lowest + 1.0

    drawing = Drawing(430, 190)
    chart = VerticalBarChart()
    chart.x = 45
    chart.y = 35
    chart.width = 350
    chart.height = 125
    chart.data = [means]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.dy = -4
    chart.valueAxis.valueMin = lowest
    chart.valueAxis.valueMax = highest * 1.2 if highest > 0 else highest
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = colors.HexColor("#4f7cff")
    chart.bars[0].strokeColor = colors.HexColor("#2f4fc4")
    drawing.add(chart)
    return _Drawing(drawing, 430, 190)


def _html_bars(summary: list[dict[str, object]]) -> str:
    if not summary:
        return ""

    items = summary[:8]
    highest = max(abs(float(item["mean"])) for item in items) or 1
    rows = "".join(
        "<div class='bar-row'>"
        f"<span class='bar-label'>{html.escape(str(item['column']))}</span>"
        "<span class='bar-track'>"
        f"<span class='bar-fill' style='width:"
        f"{abs(float(item['mean'])) / highest * 100:.1f}%'></span></span>"
        f"<span class='bar-value'>{item['mean']}</span>"
        "</div>"
        for item in items
    )
    return f"<h2>Mean by column</h2><div class='bars'>{rows}</div>"


def _safe_url(value: object) -> str:
    url = str(value or "").strip()
    return url if url.startswith(("http://", "https://")) else "#"


def _render_pdf(
    path: Path,
    title: str,
    paragraphs: list[str],
    source_filename: str,
    headers: list[str],
    body: list[list[str]],
    summary: list[dict[str, object]],
    insights: list[str],
    chart: _Drawing | None,
    sources: list[dict[str, str]],
    citations: list[dict[str, str]],
) -> None:
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"].clone("body")
    body_style.fontSize = 9.5
    body_style.leading = 13
    body_style.spaceAfter = 7
    cell_style = styles["BodyText"].clone("cell")
    cell_style.fontSize = 7
    cell_style.leading = 9
    cell_style.wordWrap = "CJK"
    story: list[object] = [
        Paragraph(_pdf_markup(title), styles["Title"]),
        Spacer(1, 0.3 * cm),
    ]

    meta = f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    if source_filename:
        meta += f" | Source: {source_filename}"
    story.append(Paragraph(_pdf_markup(meta), styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    story.append(
        Paragraph("Research overview" if sources else "Overview", styles["Heading2"])
    )
    heading_style = styles["Heading3"].clone("h3")
    heading_style.fontSize = 11
    heading_style.leading = 14
    heading_style.spaceBefore = 8
    heading_style.spaceAfter = 4
    bullet_style = body_style.clone("bullet")
    bullet_style.leftIndent = 14
    bullet_style.bulletIndent = 4
    bullet_style.spaceAfter = 3
    for paragraph in paragraphs:
        heading = re.match(
            r"^(Direct answer|Key facts|Details):\s*(.*)$", paragraph, re.IGNORECASE
        )
        if heading:
            story.append(Paragraph(heading.group(1).title(), heading_style))
            rest = heading.group(2).strip()
            if rest:
                story.append(Paragraph(_pdf_markup(rest), body_style))
        elif paragraph.startswith("- "):
            story.append(
                Paragraph(_pdf_markup(paragraph[2:]), bullet_style, bulletText="-")
            )
        else:
            story.append(Paragraph(_pdf_markup(paragraph), body_style))
    story.append(Spacer(1, 0.2 * cm))

    if sources:
        story.append(Paragraph("Web sources", styles["Heading2"]))
        source_data: list[list[object]] = [["#", "Source", "URL"]]
        for index, item in enumerate(sources, start=1):
            label = f"<b>{_pdf_markup(item.get('title', ''))}</b>"
            snippet = _pdf_text(item.get("snippet", ""))
            if snippet:
                label += f"<br/><font size='6.5'>{xml_escape(snippet[:320])}</font>"
            source_data.append(
                [
                    str(index),
                    Paragraph(label, cell_style),
                    Paragraph(_pdf_markup(item.get("url", "")), cell_style),
                ]
            )
        source_table = Table(
            source_data,
            colWidths=[0.9 * cm, 8.2 * cm, 6.9 * cm],
            repeatRows=1,
        )
        source_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d3ea")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f4f7ff")],
                    ),
                ]
            )
        )
        story.append(source_table)
        story.append(Spacer(1, 0.4 * cm))

    if citations:
        story.append(Paragraph("Cited sources", styles["Heading2"]))
        for index, item in enumerate(citations, start=1):
            label = _pdf_markup(item.get("title", "Untitled"))
            url = _pdf_markup(item.get("url", ""))
            story.append(Paragraph(f"[{index}] {label}<br/>{url}", cell_style))
        story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Key insights", styles["Heading2"]))
    for line in insights:
        story.append(Paragraph(_pdf_markup(line), bullet_style, bulletText="-"))
    story.append(Spacer(1, 0.4 * cm))

    if chart is not None:
        story.append(Paragraph("Mean by column", styles["Heading2"]))
        story.append(chart)
        story.append(Spacer(1, 0.4 * cm))

    if headers:
        story.append(Paragraph("Data preview", styles["Heading2"]))
        shown_headers = headers[:8]
        shown_body = body[:20]

        table_data: list[list[object]] = [
            [Paragraph(_pdf_markup(name), cell_style) for name in shown_headers]
        ]
        for row in shown_body:
            table_data.append(
                [
                    Paragraph(
                        _pdf_markup(row[index]) if index < len(row) else "",
                        cell_style,
                    )
                    for index in range(len(shown_headers))
                ]
            )

        width = (A4[0] - 4 * cm) / max(1, len(shown_headers))
        table = Table(
            table_data,
            colWidths=[width] * len(shown_headers),
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d3ea")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f4f7ff")],
                    ),
                ]
            )
        )
        story.append(table)

        if len(body) > len(shown_body):
            story.append(Spacer(1, 0.2 * cm))
            story.append(
                Paragraph(
                    _pdf_markup(f"Showing {len(shown_body)} of {len(body)} rows."),
                    styles["Italic"],
                )
            )
        story.append(Spacer(1, 0.4 * cm))

    if summary:
        story.append(Paragraph("Numeric summary", styles["Heading2"]))
        table_data = [["Column", "Count", "Missing", "Mean", "Median", "Min", "Max", "Std"]]
        for item in summary:
            table_data.append(
                [
                    str(item["column"]),
                    str(item["count"]),
                    str(item["missing"]),
                    str(item["mean"]),
                    str(item["median"]),
                    str(item["min"]),
                    str(item["max"]),
                    str(item["std"]),
                ]
            )
        table = Table(table_data, hAlign="LEFT", repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d3ea")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(table)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=_pdf_text(title),
    )
    doc.build(story)


def _render_html(
    path: Path,
    title: str,
    paragraphs: list[str],
    source_filename: str,
    headers: list[str],
    body: list[list[str]],
    summary: list[dict[str, object]],
    insights: list[str],
    sources: list[dict[str, str]],
    citations: list[dict[str, str]],
) -> None:
    def esc(value: object) -> str:
        return html.escape(_clean_text(value))

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data_html = ""
    if headers:
        shown_headers = headers[:8]
        head = "".join(f"<th>{esc(name)}</th>" for name in shown_headers)
        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{esc(row[index]) if index < len(row) else ''}</td>"
                for index in range(len(shown_headers))
            )
            + "</tr>"
            for row in body[:20]
        )
        note = (
            f"<p class='muted'>Showing {min(20, len(body))} of {len(body)} rows.</p>"
            if len(body) > 20
            else ""
        )
        data_html = (
            f"<h2>Data preview</h2><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table>{note}"
        )

    summary_html = ""
    if summary:
        rows = "".join(
            "<tr>"
            f"<td>{esc(item['column'])}</td><td>{esc(item['count'])}</td>"
            f"<td>{esc(item['missing'])}</td><td>{esc(item['mean'])}</td>"
            f"<td>{esc(item['median'])}</td><td>{esc(item['min'])}</td>"
            f"<td>{esc(item['max'])}</td><td>{esc(item['std'])}</td></tr>"
            for item in summary
        )
        summary_html = (
            "<h2>Numeric summary</h2><table><thead><tr>"
            "<th>Column</th><th>Count</th><th>Missing</th><th>Mean</th>"
            "<th>Median</th><th>Min</th><th>Max</th><th>Std</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    insights_html = "".join(f"<li>{esc(line)}</li>" for line in insights)
    bars_html = _html_bars(summary)

    def overview_markup(items: list[str]) -> str:
        parts: list[str] = []
        in_list = False
        for item in items:
            text = item.strip()
            heading = re.match(
                r"^(Direct answer|Key facts|Details):\s*(.*)$", text, re.IGNORECASE
            )
            if heading:
                if in_list:
                    parts.append("</ul>")
                    in_list = False
                name = heading.group(1).title()
                rest = heading.group(2).strip()
                parts.append(f"<h3>{esc(name)}</h3>")
                if rest:
                    parts.append(f"<p>{esc(rest)}</p>")
                if name.lower() == "key facts":
                    parts.append("<ul>")
                    in_list = True
                continue
            if text.startswith("- "):
                if not in_list:
                    parts.append("<ul>")
                    in_list = True
                parts.append(f"<li>{esc(text[2:])}</li>")
            else:
                if in_list:
                    parts.append("</ul>")
                    in_list = False
                parts.append(f"<p>{esc(text)}</p>")
        if in_list:
            parts.append("</ul>")
        return "".join(parts)

    overview_html = overview_markup(paragraphs)
    overview_title = "Research overview" if sources else "Overview"
    sources_badge = (
        f'<span class="badge">{len(sources)} sources</span>' if sources else ""
    )
    data_badges = ""
    if headers or body:
        data_badges = (
            f'<span class="badge">{len(body)} rows</span>'
            f'<span class="badge">{len(headers)} columns</span>'
            f'<span class="badge">{len(summary)} numeric</span>'
        )
    citations_html = ""
    if citations:
        items = "".join(
            f'<li><a href="{esc(_safe_url(item.get("url", "")))}">'
            f'[{index}] {esc(item.get("title", "Untitled"))}</a></li>'
            for index, item in enumerate(citations, start=1)
        )
        citations_html = f"<h2>Cited sources</h2><ul>{items}</ul>"

    insights_section = (
        f"<h2>Key insights</h2><ul>{insights_html}</ul>" if insights else ""
    )

    sources_html = ""
    if sources:
        rows = "".join(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{esc(item.get('title', ''))}</td>"
            f"<td><a href='{esc(_safe_url(item.get('url')))}'>"
            f"{esc(item.get('url', ''))}</a></td>"
            f"<td>{esc(item.get('snippet', ''))}</td>"
            "</tr>"
            for index, item in enumerate(sources, start=1)
        )
        sources_html = (
            "<h2>Web sources</h2><table><thead><tr>"
            "<th>#</th><th>Title</th><th>URL</th><th>Snippet</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title>
<style>
  :root {{ --ink: #172038; --muted: #6b7691; --line: #d7deee; --accent: #4f7cff; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
         margin: 0; padding: 40px 20px; background: #f6f8fe; color: var(--ink);
         line-height: 1.55; }}
  main {{ max-width: 980px; margin: 0 auto; background: white; padding: 36px 42px;
          border: 1px solid var(--line); border-radius: 18px;
          box-shadow: 0 20px 60px rgba(23, 32, 56, 0.08); }}
  h1 {{ margin: 0 0 6px; font-size: 30px; letter-spacing: -0.02em; }}
  h2 {{ margin-top: 30px; border-bottom: 1px solid var(--line); padding-bottom: 5px;
        font-size: 18px; }}
  .muted {{ color: var(--muted); font-size: 13px; }}
  .badge {{ display: inline-block; background: #e8efff; color: #2f4fc4;
            border-radius: 999px; padding: 3px 10px; font-size: 12px;
            font-weight: 700; margin-right: 6px; }}
  pre {{ background: #f4f7ff; padding: 14px; border-radius: 10px; white-space: pre-wrap; }}
  .prose p {{ margin: 0 0 12px; }}
  .prose h3 {{ margin: 18px 0 6px; font-size: 15px; color: #2f4fc4; }}
  ul {{ padding-left: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 13px; }}
  th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: left;
            vertical-align: top; }}
  th {{ background: #1f2a44; color: white; }}
  tr:nth-child(even) td {{ background: #f7f9ff; }}
  .bars {{ display: grid; gap: 8px; margin-top: 12px; }}
  .bar-row {{ display: grid; grid-template-columns: 150px 1fr 70px; gap: 10px;
              align-items: center; font-size: 13px; }}
  .bar-label {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .bar-track {{ height: 12px; background: #e8efff; border-radius: 999px;
                overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; background: linear-gradient(90deg,
                #4f7cff, #8a6bff); }}
  .bar-value {{ text-align: right; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<main>
<h1>{esc(title)}</h1>
<p class="muted">Generated: {esc(generated)}"""
    if source_filename:
        document += f" | Source: {esc(source_filename)}"
    document += f"""</p>
<p>{data_badges}{sources_badge}</p>
<h2>{overview_title}</h2>
<div class="prose">{overview_html}</div>
{sources_html}
{citations_html}
{insights_section}
{bars_html}
{data_html}
{summary_html}
</main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


@mcp.tool()
def generate_report(
    title: str,
    content: str,
    data: str = "",
    source_filename: str = "",
    sources: list[dict] | None = None,
    citations: list[dict] | None = None,
) -> str:
    """Generate a real PDF + HTML report with optional data and web sources."""
    title = _clean_text(title, 200) or "Mini AI Agent Report"
    content = _clean_text(content, 20_000)
    data = (data or "").strip()[:200000]
    clean_sources = [
        {
            "title": _clean_text(item.get("title", ""), 200),
            "url": str(item.get("url", "")).strip()[:500],
            "snippet": _clean_text(item.get("snippet", ""), 500),
        }
        for item in (sources or [])
        if isinstance(item, dict) and str(item.get("url", "")).strip()
    ][:8]
    clean_citations = [
        {
            "title": _clean_text(item.get("title", ""), 200),
            "url": str(item.get("url", "") or "").strip()[:500],
        }
        for item in (citations or [])
        if isinstance(item, dict) and str(item.get("url", "") or "").strip()
    ][:8]

    headers, body = _parse_data(data) if data else ([], [])
    summary = _numeric_summary(headers, body)
    insights = _insights(headers, body, summary) if (headers or body) else []
    if clean_sources:
        insights.append(
            f"{len(clean_sources)} web sources were used to build this report."
        )
    chart = _mean_chart(summary)
    bare_request = re.match(
        r"(?i)^(generate|create|make|write|rapport|report)\b", content.strip()
    )
    if (headers or body) and bare_request and len(content.strip()) < 120:
        content = (
            f"This report analyzes {source_filename or 'the provided dataset'} "
            f"({len(body)} rows, {len(headers)} columns)."
        )
    paragraphs = _prepare_paragraphs(content, clean_sources)

    base = f"report-{uuid.uuid4().hex[:10]}"
    pdf_path = ARTIFACTS_DIR / f"{base}.pdf"
    html_path = ARTIFACTS_DIR / f"{base}.html"

    _render_pdf(
        pdf_path,
        title,
        paragraphs,
        source_filename,
        headers,
        body,
        summary,
        insights,
        chart,
        clean_sources,
        clean_citations,
    )
    _render_html(
        html_path,
        title,
        paragraphs,
        source_filename,
        headers,
        body,
        summary,
        insights,
        clean_sources,
        clean_citations,
    )

    payload = {
        "status": "generated",
        "title": title,
        "source_filename": source_filename,
        "summary": {
            "rows": len(body),
            "columns": len(headers),
            "numeric": summary,
            "insights": insights,
        },
        "sources": clean_sources,
        "files": [
            {
                "kind": "pdf",
                "filename": pdf_path.name,
                "size": pdf_path.stat().st_size,
            },
            {
                "kind": "html",
                "filename": html_path.name,
                "size": html_path.stat().st_size,
            },
        ],
    }
    print(f"[REPORT GENERATED] {payload}", flush=True)
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
