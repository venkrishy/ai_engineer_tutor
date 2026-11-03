"""Grade a folder holding main.py against one level of a local bundle, in a real
AgentCore Code Interpreter session: python3 scripts/smoke_room.py assignments/triage Reply my_solution/"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tutor.catalog import LevelAssets, compile_checker
from tutor.clerk import StudentCard
from tutor.grading import Submission
from tutor.rooms import AgentCoreRoom


def main(argv: list[str]) -> int:
    bundle, level, solution = Path(argv[1]), argv[2], Path(argv[3])
    for folder in sorted((bundle / "levels").iterdir()):
        if json.loads((folder / "level.json").read_text())["name"] == level:
            break
    else:
        print(f"no level named {level}")
        return 1
    tickets = json.loads((folder / "tickets.json").read_text())
    checker = folder / "checker.py"
    assets = LevelAssets(tickets, compile_checker(checker.read_text() if checker.exists() else None))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(solution.rglob("*")):
            if path.is_file():
                archive.writestr(path.relative_to(solution).as_posix(), path.read_bytes())
    cards = {"me@example.com": StudentCard(email="me@example.com", open_level=level)}
    room = AgentCoreRoom(
        boto3.client("bedrock-agentcore", region_name="us-east-1"),
        cards,
        {"m1": buffer.getvalue()},
        lambda assignment_id, name: assets,
    )
    print(room.grade(Submission("me@example.com", "m1")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
