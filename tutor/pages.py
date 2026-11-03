"""Build the two static pages of a level from its bundle folder.

Each level folder gets assignment.html (the goal, samples, rules, how to test, what to zip) and
hints-and-help.html (tiered hints, the one-shot prompt, how to build it with a coding tool).
The files are published by GitHub Pages and linked from the emails (see tutor/links.py).

Beside the files the catalog reads, a level folder may hold:

  rules.md       the rules the checker applies, in plain words
  samples.json   [{"input": {...}, "output": {...}}], public examples
  hints.md       one hint per failed try, separated by lines of ---

The samples are public because this repository is public. They must not be the hidden tickets.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from tutor.links import ASSIGNMENT_PAGE, HINTS_PAGE, level_folder
from tutor.render import to_html

STYLE = """
:root{--ink:#17262c;--muted:#5b6b72;--accent:#0b5cad;--line:#d9e0e3;--bg:#f4f6f7;--card:#fff;--soft:#eaf3fc;--code:#f3f6f8}
@media (prefers-color-scheme:dark){:root{--ink:#e6edf0;--muted:#9fb0b8;--accent:#6aaeea;--line:#2b3b42;--bg:#0f171b;--card:#162228;--soft:#14283a;--code:#0d1519}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,Segoe UI,Helvetica,Arial,sans-serif}
header{background:var(--accent);color:#fff;padding:14px 16px}
header div,main{max-width:760px;margin:0 auto}
header strong{font-size:17px}
main{padding:20px 16px 48px}
.crumb{color:var(--muted);font-size:14px;margin:0 0 4px}
h1{font-size:28px;line-height:1.25;margin:4px 0 14px}
h2{font-size:20px;margin:30px 0 10px}
section,.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:14px 0}
pre{margin:8px 0;padding:12px 14px;background:var(--code);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:4px;overflow-x:auto;font:13px/1.5 Menlo,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
code{font:13px Menlo,Consolas,monospace;background:var(--code);padding:1px 5px;border-radius:3px}
pre code{background:none;padding:0}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:640px){.pair{grid-template-columns:1fr}h1{font-size:24px}}
.label{font-size:12.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
nav a,.button{display:inline-block;margin:0 8px 8px 0;padding:8px 14px;border-radius:6px;border:1px solid var(--accent);color:var(--accent);text-decoration:none;font-weight:600;background:transparent;font-size:15px;cursor:pointer}
a{color:var(--accent)}
.button.primary,nav a.primary{background:var(--accent);color:#fff}
details{margin:10px 0;border:1px solid var(--line);border-radius:6px;padding:10px 14px;background:var(--card)}
summary{cursor:pointer;font-weight:600}
.note{background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:10px 14px;margin:12px 0}
"""

TOOL_STEPS = "\n".join(
    [
        "**With Claude Code**",
        "",
        "1. Install it: `curl -fsSL https://claude.ai/install.sh | bash`",
        "2. Make an empty folder and start Claude Code in it: `mkdir {slug} && cd {slug} && claude`",
        "3. Paste the whole prompt from the box above. Claude Code writes `main.py`, tests it, and creates `{zip}` for you.",
        "4. Check that `{zip}` is in the folder. If it is not, run `zip {zip} main.py`.",
        "5. Reply to the tutor's email with `{zip}` attached.",
        "",
        "**With GitHub Copilot**",
        "",
        "1. Install Visual Studio Code and the GitHub Copilot extension, then sign in to GitHub.",
        "2. Open an empty folder (File > Open Folder).",
        "3. Open the Copilot Chat view and switch the mode to Agent.",
        "4. Paste the whole prompt from the box above. Copilot writes `main.py`, tests it, and creates `{zip}` for you.",
        "5. Check that `{zip}` is in the folder. If it is not, run `zip {zip} main.py`.",
        "6. Reply to the tutor's email with `{zip}` attached.",
    ]
)


@dataclass(frozen=True)
class LevelPage:
    assignment_id: str
    assignment_name: str
    position: int
    total: int
    name: str
    title: str
    context: str
    instructions: str
    prompt: str
    rules: str
    samples: tuple[dict, ...]
    hints: tuple[str, ...]

    @property
    def zip_name(self) -> str:
        return f"{self.name.lower()}.zip"

    @property
    def folder(self) -> str:
        return level_folder(self.position, self.name)


def _json(value: object) -> str:
    return json.dumps(value, indent=2)


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _shell(sample: dict) -> str:
    """A command a student can paste into a terminal to try one sample."""
    return f"echo '{json.dumps(sample['input'])}' | python3 main.py"


def _document(title: str, body: str, script: str = "") -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_escape(title)}</title><style>{STYLE}</style></head><body>"
        '<header><div><strong>AI Engineers Course</strong></div></header>'
        f"<main>{body}</main>{script}</body></html>\n"
    )


def _nav(page: LevelPage, here: str) -> str:
    other = HINTS_PAGE if here == ASSIGNMENT_PAGE else ASSIGNMENT_PAGE
    label = "Hints and help" if here == ASSIGNMENT_PAGE else "Assignment"
    return f'<nav><a class="primary" href="{other}">{label}</a></nav>'


def _heading(page: LevelPage, kind: str) -> str:
    return (
        f'<p class="crumb">{_escape(page.assignment_name)} &middot; Level {page.position} of {page.total} '
        f"({_escape(page.name)}) &middot; {kind}</p><h1>{_escape(page.title)}</h1>"
    )


def _tree(page: LevelPage) -> str:
    return (
        f"{page.zip_name}\n└── main.py\n\n"
        f"Also fine, with one folder inside:\n\n{page.zip_name}\n└── {page.name.lower()}/\n    └── main.py"
    )


def assignment_page(page: LevelPage) -> str:
    examples = "".join(
        f'<div class="card"><div class="pair"><div><div class="label">Input, example {number}</div>'
        f"<pre>{_escape(_json(sample['input']))}</pre></div>"
        f'<div><div class="label">Output, example {number}</div>'
        f"<pre>{_escape(_json(sample['output']))}</pre></div></div></div>"
        for number, sample in enumerate(page.samples, start=1)
    )
    first = page.samples[0]
    body = "".join(
        [
            _heading(page, "Assignment"),
            _nav(page, ASSIGNMENT_PAGE),
            f"<section>{to_html(page.context)}</section>" if page.context else "",
            f"<section>{to_html(page.instructions)}</section>",
            "<h2>What your program reads and prints</h2>",
            to_html(
                "Your program is `main.py`. The grader runs it once per ticket with `python3 main.py`, "
                "sends the ticket as JSON on standard input, and reads standard output. "
                "Print exactly one JSON object and nothing else."
            ),
            examples,
            '<p class="note">These are examples. The grader checks your program on five other tickets you have not seen, '
            "so your program must follow the rules, not remember the examples."
            + (" Your reply wording can differ from the example; the checker tests its rules." if "reply" in first["output"] else "")
            + "</p>",
            f"<h2>The rules</h2><section>{to_html(page.rules)}</section>" if page.rules else "",
            "<h2>How to test it</h2>",
            to_html("Run one of the examples from a terminal in the folder that holds `main.py`:"),
            f"<pre>{_escape(_shell(first))}</pre>",
            to_html("You should see:"),
            f"<pre>{_escape(json.dumps(first['output']))}</pre>",
            f"<h2>What to send back</h2>{to_html('Zip your program and reply to the tutor email with the zip attached. One zip per email, 10 MB or less. The grader needs `main.py` at the top of the zip, or inside a single folder.')}",
            f"<pre>{_escape(_tree(page))}</pre>",
            to_html(f"On a Mac or Linux, `zip {page.zip_name} main.py` makes it."),
            _nav(page, ASSIGNMENT_PAGE),
        ]
    )
    return _document(f"{page.title} - Assignment", body)


COPY_SCRIPT = """<script>
async function copyPrompt(button) {
  const node = document.getElementById("prompt");
  try { await navigator.clipboard.writeText(node.textContent); button.textContent = "Copied"; }
  catch (error) {
    const range = document.createRange(); range.selectNodeContents(node);
    const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
    button.textContent = "Selected. Press Ctrl+C or Cmd+C";
  }
}
</script>"""


def hints_page(page: LevelPage) -> str:
    hints = "".join(
        f"<details><summary>Hint {number}</summary>{to_html(text)}</details>"
        for number, text in enumerate(page.hints, start=1)
    ) or "<p>No hints for this level yet. Compare your output with the examples on the Assignment page.</p>"
    steps = TOOL_STEPS.format(zip=page.zip_name, slug=page.name.lower())
    body = "".join(
        [
            _heading(page, "Hints and help"),
            _nav(page, HINTS_PAGE),
            to_html("**Try it on your own first.** Open a hint only when you are stuck. The hints grow in strength and none of them gives the answer."),
            f"<h2>Hints</h2>{hints}",
            "<h2>Still stuck? Use the prompt</h2>",
            to_html("Copy the prompt below and paste it into your coding tool exactly as it is. It holds the whole task, so you do not need to add anything."),
            f'<pre id="prompt">{_escape(page.prompt)}</pre>',
            '<button class="button primary" type="button" onclick="copyPrompt(this)">Copy the prompt</button>',
            "<h2>Build it with a coding tool</h2>",
            f"<section>{to_html(steps)}</section>",
            _nav(page, HINTS_PAGE),
        ]
    )
    return _document(f"{page.title} - Hints and help", body, COPY_SCRIPT)


def _split_hints(text: str) -> tuple[str, ...]:
    return tuple(tier.strip() for tier in re.split(r"\n\s*---\s*\n", text) if tier.strip())


def load_level_pages(assignment_dir: Path) -> list[LevelPage]:
    """Read every level folder of an assignment folder."""
    meta = json.loads((assignment_dir / "assignment.json").read_text())
    folders = sorted(path for path in (assignment_dir / "levels").iterdir() if path.is_dir())
    pages = []
    for position, folder in enumerate(folders, start=1):
        def text(name: str) -> str:
            path = folder / name
            return path.read_text().strip() if path.exists() else ""

        info = json.loads((folder / "level.json").read_text())
        samples = json.loads(text("samples.json") or "[]")
        if not samples:
            raise ValueError(f"{folder.name}/samples.json is missing or empty")
        pages.append(
            LevelPage(
                meta["id"],
                meta["name"],
                position,
                len(folders),
                info["name"],
                info.get("title") or info["name"],
                text("context.md"),
                text("instructions.md"),
                text("prompt.md"),
                text("rules.md"),
                tuple(samples),
                _split_hints(text("hints.md")),
            )
        )
    return pages


def write_pages(assignment_dir: Path) -> list[Path]:
    written = []
    for page in load_level_pages(assignment_dir):
        folder = assignment_dir / "levels" / page.folder
        if not folder.is_dir():
            raise ValueError(f"the level folder must be named {page.folder} so the email links work")
        for filename, content in (
            (ASSIGNMENT_PAGE, assignment_page(page)),
            (HINTS_PAGE, hints_page(page)),
        ):
            (folder / filename).write_text(content)
            written.append(folder / filename)
    return written
