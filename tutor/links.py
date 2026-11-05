"""Where the Assignment and Hints and help pages of one level are published.

The pages are static HTML files in this repository, one folder per level, served by GitHub Pages.
"""

from __future__ import annotations

import re

BASE_URL = "https://venkrishy.github.io/ai_engineer_tutor/assignments"
ASSIGNMENT_PAGE = "assignment.html"
HINTS_PAGE = "hints-and-help.html"


def level_folder(position: int, name: str) -> str:
    """The folder name of a level, such as 01-classify. Position counts from 1."""
    return f"{position:02d}-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}"


def assignment_url(assignment_id: str, position: int, name: str) -> str:
    return f"{BASE_URL}/{assignment_id}/levels/{level_folder(position, name)}/{ASSIGNMENT_PAGE}"


def hints_url(assignment_id: str, position: int, name: str) -> str:
    return f"{BASE_URL}/{assignment_id}/levels/{level_folder(position, name)}/{HINTS_PAGE}"
