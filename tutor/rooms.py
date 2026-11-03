"""The door and the room: a no-op door, and a room that grades in AgentCore Code Interpreter."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from tutor.grading import DoorOrder, RoomResult, Submission
from tutor.judge import Run, judge


class NullDoor:
    """No private door is needed: the room has no network of its own."""

    def start_create(self, order: DoorOrder) -> str:
        return "no-door"

    def status(self, endpoint_id: str) -> str:
        return "available"

    def delete(self, endpoint_id: str) -> None:
        return None


class UngradedRoom:
    def grade(self, submission: Submission) -> RoomResult:
        return RoomResult.NOT_GRADED


UNPACK = """\
import os, sys, zipfile
archive = zipfile.ZipFile("work.zip")
for name in archive.namelist():
    if name.startswith("/") or ".." in name.split("/"):
        sys.exit("unsafe path in zip")
archive.extractall("app")
top = [name for name in os.listdir("app") if not name.startswith("__MACOSX")]
home = "app"
if not os.path.exists("app/main.py") and len(top) == 1 and os.path.exists(f"app/{top[0]}/main.py"):
    home = f"app/{top[0]}"
print(os.path.abspath(home) if os.path.exists(f"{home}/main.py") else "NOMAIN")
"""


@dataclass(frozen=True)
class RoomGrade:
    result: RoomResult
    findings: str = ""


class AgentCoreRoom:
    """Grade one zip in an AgentCore Code Interpreter session that has no internet."""

    def __init__(
        self,
        client,
        cards,
        payloads,
        load_assets,
        *,
        interpreter: str = "aws.codeinterpreter.v1",
        budget_s: float = 170,
        per_ticket_s: int = 10,
        clock=time.monotonic,
    ) -> None:
        self._client = client
        self._cards = cards
        self._payloads = payloads
        self._load_assets = load_assets
        self._interpreter = interpreter
        self._budget_s = budget_s
        self._per_ticket_s = per_ticket_s
        self._clock = clock

    def grade(self, submission: Submission):
        card = self._cards[submission.email]
        try:
            assets = self._load_assets(card.assignment_id, card.open_level)
            payload = self._payloads[submission.message_id]
            return self._grade_in_session(assets, payload)
        except Exception:
            return RoomResult.NOT_GRADED

    def _grade_in_session(self, assets, payload: bytes):
        started = self._clock()
        session = self._client.start_code_interpreter_session(
            codeInterpreterIdentifier=self._interpreter,
            name="grade",
            sessionTimeoutSeconds=300,
        )
        session_id = session["sessionId"]
        try:
            self._call(session_id, "writeFiles", content=[{"path": "work.zip", "blob": payload}, {"path": "unpack.py", "text": UNPACK}])
            home = self._call(session_id, "executeCommand", command="python3 unpack.py").get("stdout", "").strip()
            if home.endswith("NOMAIN") or not home.startswith("/"):
                return RoomGrade(RoomResult.FAIL, "main.py was not found at the top of the zip or inside a single folder.")
            inputs = [{"path": f"tickets/{n}.json", "text": json.dumps(t["input"])} for n, t in enumerate(assets.tickets)]
            self._call(session_id, "writeFiles", content=inputs)
            counter = iter(range(len(assets.tickets)))

            def run_one(ticket_input: dict) -> Run:
                if self._clock() - started > self._budget_s:
                    raise TimeoutError("the room ran out of time")
                number = next(counter)
                done = self._call(
                    session_id,
                    "executeCommand",
                    command=f"cd {home} && timeout {self._per_ticket_s} python3 main.py < $OLDPWD/tickets/{number}.json",
                )
                code = int(done.get("exitCode", 0))
                return Run(done.get("stdout", ""), done.get("stderr", ""), 0 if code == 124 else code, code == 124)

            verdict = judge(assets, run_one)
            return RoomGrade(RoomResult.PASS if verdict.passed else RoomResult.FAIL, verdict.findings)
        finally:
            try:
                self._client.stop_code_interpreter_session(
                    codeInterpreterIdentifier=self._interpreter, sessionId=session_id
                )
            except Exception:
                pass

    def _call(self, session_id: str, name: str, **arguments) -> dict:
        response = self._client.invoke_code_interpreter(
            codeInterpreterIdentifier=self._interpreter,
            sessionId=session_id,
            name=name,
            arguments=arguments,
        )
        result: dict = {}
        for event in response["stream"]:
            body = event.get("result", {})
            if body.get("isError"):
                raise RuntimeError(str(body.get("content")))
            result = body.get("structuredContent") or {"stdout": "".join(part.get("text", "") for part in body.get("content", []))}
        return result
