"""Turn the reply text into an email with a status line and a formatted HTML part.

The text is a small markdown: **bold**, `code`, ``` fenced blocks, "- " and "1. " lists,
and blank lines between paragraphs. A line starting with "## " is a heading. The plain-text part keeps it readable as it is.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from datetime import date

from tutor.clerk import Level, StudentCard
from tutor.grading import DAILY_GRADED_ATTEMPT_CAP

STATUS_RULE = "\n\n---\n"
INK, MUTED, ACCENT, LINE = "#17262c", "#5b6b72", "#0b5cad", "#d9e0e3"
CODE_STYLE = "font-family:Menlo,Consolas,monospace;font-size:13px;background:#eef2f4;padding:1px 5px;border-radius:3px"
PRE_STYLE = (
    "font-family:Menlo,Consolas,monospace;font-size:12.5px;line-height:1.5;background:#f3f6f8;"
    f"border:1px solid {LINE};border-left:4px solid {ACCENT};border-radius:4px;padding:14px 16px;"
    "white-space:pre-wrap;word-break:break-word;margin:12px 0"
)


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", rf'<code style="{CODE_STYLE}">\1</code>', escaped)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def to_html(text: str) -> str:
    out: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    kind = ""
    code: list[str] | None = None

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f'<p style="margin:0 0 14px">{"<br>".join(_inline(line) for line in paragraph)}</p>')
            paragraph.clear()

    def flush_list() -> None:
        nonlocal kind
        if items:
            rows = "".join(f'<li style="margin:0 0 6px">{_inline(item)}</li>' for item in items)
            out.append(f'<{kind} style="margin:0 0 14px;padding-left:24px">{rows}</{kind}>')
            items.clear()
        kind = ""

    for line in text.split("\n"):
        if code is not None:
            if line.strip() == "```":
                out.append(f'<pre style="{PRE_STYLE}">{html.escape(chr(10).join(code), quote=False)}</pre>')
                code = None
            else:
                code.append(line)
            continue
        if line.strip() == "```":
            flush_paragraph(); flush_list()
            code = []
            continue
        heading = re.match(r"^## (.*)", line)
        if heading:
            flush_paragraph(); flush_list()
            out.append(f'<h2 style="font-size:19px;line-height:1.3;margin:22px 0 10px">{_inline(heading.group(1))}</h2>')
            continue
        bullet = re.match(r"^- (.*)", line)
        number = re.match(r"^\d+\. (.*)", line)
        if bullet or number:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if kind and kind != wanted:
                flush_list()
            kind = wanted
            items.append((bullet or number).group(1))
        elif not line.strip():
            flush_paragraph(); flush_list()
        elif line.strip() == "---":
            flush_paragraph(); flush_list()
            out.append(f'<hr style="border:0;border-top:1px solid {LINE};margin:20px 0">')
        else:
            flush_list()
            paragraph.append(line)
    if code is not None:
        out.append(f'<pre style="{PRE_STYLE}">{html.escape(chr(10).join(code), quote=False)}</pre>')
    flush_paragraph(); flush_list()
    return "\n".join(out)


def status_for(card: StudentCard | None, ladder: Sequence[Level], today: date) -> str:
    """One plain sentence saying where the student stands."""
    if card is None:
        return ""
    if card.finished:
        return "You have cleared every level. Well done."
    mine = [level for level in ladder if level.assignment == card.assignment_id]
    if not mine:
        return ""
    position = card.level_index(ladder)
    level = mine[position]
    name = level.assignment_name or card.assignment_id
    used = card.graded_tries_today if card.graded_day == today else 0
    left = max(0, DAILY_GRADED_ATTEMPT_CAP - used)
    return (
        f"Your status: {name}, Level {position + 1} of {len(mine)} ({level.name}). "
        f"Levels cleared: {position}. Graded tries left today: {left} of {DAILY_GRADED_ATTEMPT_CAP}."
    )


def render_reply(body: str, status: str) -> tuple[str, str]:
    """The plain-text part and the HTML part of one reply."""
    text = body + (f"{STATUS_RULE}{status}" if status else "")
    chip = ""
    if status:
        chip = (
            f'<div style="background:#eaf3fc;border:1px solid #b9d6f2;border-radius:6px;padding:10px 14px;'
            f'margin:0 0 20px;color:{INK};font-size:14px">{_inline(status).replace("Your status:", "<strong>Your status:</strong>")}</div>'
        )
    page = (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f4f6f7">'
        f'<div style="max-width:660px;margin:0 auto;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        f'font-size:15px;line-height:1.55;color:{INK}">'
        f'<div style="background:{ACCENT};color:#fff;padding:16px 24px;font-size:16px;font-weight:600">AI Engineers Course</div>'
        f'<div style="background:#fff;padding:24px;border:1px solid {LINE};border-top:0">{chip}{to_html(body)}</div>'
        f'<div style="padding:14px 24px;color:{MUTED};font-size:12.5px">'
        "Reply to this email with your zip attached. Each reply stays on the same thread.</div>"
        "</div></body></html>"
    )
    return text, page
