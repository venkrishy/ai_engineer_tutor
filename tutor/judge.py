"""Run a student's program on the hidden tickets and decide pass or fail.

The answer key stays here. The program only ever sees each ticket's input.
Four of five tickets must pass.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable

from tutor.catalog import LevelAssets

PASS_SHARE = 0.8


@dataclass(frozen=True)
class Run:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False


@dataclass(frozen=True)
class Verdict:
    passed: bool
    findings: str


def _one_object(stdout: str):
    try:
        value = json.loads(stdout.strip())
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _problems(assets: LevelAssets, ticket: dict, run: Run) -> list[str]:
    if run.timed_out:
        return ["the program took too long"]
    if run.exit_code != 0:
        return ["the program crashed: " + run.stderr.strip()[-300:]]
    output = _one_object(run.stdout)
    if output is None:
        return ["the output is not exactly one JSON object"]
    return assets.checker(ticket, output)


def judge(assets: LevelAssets, run_one: Callable[[dict], Run]) -> Verdict:
    needed = math.ceil(PASS_SHARE * len(assets.tickets))
    lines: list[str] = []
    passed = 0
    for number, ticket in enumerate(assets.tickets, start=1):
        problems = _problems(assets, ticket, run_one(ticket["input"]))
        if not problems:
            passed += 1
            continue
        subject = ticket["input"].get("subject", "")
        lines.append(f"Ticket {number} ({subject}): " + "; ".join(problems))
    if passed >= needed:
        return Verdict(True, "")
    summary = f"{passed} of {len(assets.tickets)} tickets passed; {needed} are needed."
    return Verdict(False, "\n".join([summary, *lines]))
