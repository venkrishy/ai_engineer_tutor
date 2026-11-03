"""Build the Assignment and Hints and help pages of an assignment folder.

  python3 scripts/build_pages.py assignments/triage

Commit the generated .html files. GitHub Pages publishes them and the emails link to them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tutor.pages import write_pages


def main(argv: list[str]) -> int:
    for path in write_pages(Path(argv[1])):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
