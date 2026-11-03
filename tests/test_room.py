import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_catalog import fake_tickets

from tutor.catalog import LevelAssets, match_expected
from tutor.clerk import StudentCard
from tutor.grading import RoomResult, Submission
from tutor.rooms import AgentCoreRoom, RoomGrade


class FakeSandbox:
    """Answers each ticket with the expected answer, unless told to misbehave."""

    def __init__(self, tickets, *, home="/data/app", broken=False, fail_on=None):
        self.tickets = tickets
        self.home = home
        self.broken = broken
        self.fail_on = fail_on
        self.calls = []
        self.started = 0
        self.stopped = 0
        self.written = []

    def start_code_interpreter_session(self, **kwargs):
        self.started += 1
        return {"sessionId": "s1"}

    def stop_code_interpreter_session(self, **kwargs):
        self.stopped += 1

    def invoke_code_interpreter(self, *, codeInterpreterIdentifier, sessionId, name, arguments):
        self.calls.append((name, arguments))
        if self.fail_on == name:
            raise RuntimeError("throttled")
        if name == "writeFiles":
            self.written.extend(arguments["content"])
            out = {"content": [{"type": "text", "text": "ok"}]}
        elif "unpack.py" in arguments.get("command", ""):
            out = {"structuredContent": {"stdout": self.home + "\n" if not self.broken else "NOMAIN\n", "exitCode": 0}}
        else:
            number = int(arguments["command"].rsplit("/", 1)[1].split(".")[0])
            ticket = self.tickets[number]
            out = {"structuredContent": {"stdout": json.dumps(dict(ticket["expected"], id=ticket["input"]["id"])), "stderr": "", "exitCode": 0}}
        return {"stream": [{"result": dict(out, isError=False)}]}


def room_for(sandbox, tickets, clock=lambda: 0.0, budget_s=170):
    cards = {"a@example.com": StudentCard(email="a@example.com", open_level="Route")}
    assets = LevelAssets(tickets, match_expected)
    loaded = []

    def load_assets(assignment_id, level):
        loaded.append((assignment_id, level))
        return assets

    room = AgentCoreRoom(sandbox, cards, {"m1": b"zipbytes"}, load_assets, clock=clock, budget_s=budget_s)
    return room, loaded


class AgentCoreRoomTest(unittest.TestCase):
    def setUp(self):
        self.tickets = fake_tickets("02-route")
        self.submission = Submission("a@example.com", "m1")

    def test_a_good_zip_passes_and_the_session_is_stopped(self):
        sandbox = FakeSandbox(self.tickets)
        room, loaded = room_for(sandbox, self.tickets)

        grade = room.grade(self.submission)

        self.assertEqual(grade, RoomGrade(RoomResult.PASS, ""))
        self.assertEqual((sandbox.started, sandbox.stopped), (1, 1))
        self.assertEqual(loaded, [("triage", "Route")])

    def test_the_answer_key_never_enters_the_session(self):
        sandbox = FakeSandbox(self.tickets)
        room, _ = room_for(sandbox, self.tickets)

        room.grade(self.submission)

        sent = json.dumps([call for call in sandbox.calls], default=str)
        self.assertNotIn("expected", sent)
        self.assertNotIn('"P1"', sent)

    def test_a_zip_without_main_py_fails_with_a_clear_finding(self):
        sandbox = FakeSandbox(self.tickets, broken=True)
        room, _ = room_for(sandbox, self.tickets)

        grade = room.grade(self.submission)

        self.assertEqual(grade.result, RoomResult.FAIL)
        self.assertIn("main.py was not found", grade.findings)
        self.assertEqual(sandbox.stopped, 1)

    def test_a_room_error_is_not_graded_and_the_session_is_still_stopped(self):
        sandbox = FakeSandbox(self.tickets, fail_on="executeCommand")
        room, _ = room_for(sandbox, self.tickets)

        self.assertEqual(room.grade(self.submission), RoomResult.NOT_GRADED)
        self.assertEqual(sandbox.stopped, 1)

    def test_running_out_of_time_is_not_graded(self):
        sandbox = FakeSandbox(self.tickets)
        ticks = iter([0.0, 1.0, 999.0, 999.0, 999.0, 999.0, 999.0, 999.0])
        room, _ = room_for(sandbox, self.tickets, clock=lambda: next(ticks))

        self.assertEqual(room.grade(self.submission), RoomResult.NOT_GRADED)
        self.assertEqual(sandbox.stopped, 1)

    def test_a_missing_assignment_is_not_graded(self):
        sandbox = FakeSandbox(self.tickets)
        room, _ = room_for(sandbox, self.tickets)
        room._load_assets = lambda *_: (_ for _ in ()).throw(LookupError("gone"))

        self.assertEqual(room.grade(self.submission), RoomResult.NOT_GRADED)
        self.assertEqual(sandbox.started, 0)


if __name__ == "__main__":
    unittest.main()
