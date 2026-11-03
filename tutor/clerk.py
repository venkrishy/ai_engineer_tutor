"""Turn a letter into one reply and the updated student card.

A first letter creates the student and replies with a welcome, the first
level, and step-by-step instructions for a first submission.
A zip on that letter is ignored. A later accepted zip is one submission:
the tutor grades it through the batch and replies on the same thread.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Protocol

from tutor.grading import (
    Door,
    Outcome,
    Quota,
    Room,
    RoomResult,
    Submission,
    run_batch,
)

@dataclass(frozen=True)
class Level:
    name: str
    instructions: str

    @property
    def body(self) -> str:
        return f"{self.name}\n\n{self.instructions}"


HOW_IT_RUNS = "Your program is main.py. The grader runs it once per ticket with `python3 main.py`, sends the ticket as JSON on standard input, and reads standard output. Print exactly one JSON object and nothing else."

LADDER = (
    Level(
        name="Classify",
        instructions="\n".join(
            [
                "Read one ticket as JSON and print one JSON object with the ticket id and a label: bug, billing, access, or other.",
                "",
                HOW_IT_RUNS,
                "",
                "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
                "",
                "Sample ticket:",
                '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
            ]
        ),
    ),
    Level(
        name="Route",
        instructions="\n".join(
            [
                "Read one ticket as JSON and print one JSON object with the ticket id, a label (bug, billing, access, or other), a priority (P1, P2, P3), and a queue.",
                "",
                HOW_IT_RUNS,
                "",
                "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
                "",
                "Bugs go to engineering, billing goes to billing, and the rest go to support. P1 means work is blocked or money is wrong. P3 is a how-to. P2 is the rest.",
                "",
                "Sample ticket:",
                '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
            ]
        ),
    ),
    Level(
        name="Reply",
        instructions="\n".join(
            [
                "Read one ticket as JSON and print one JSON object with the ticket id, a label (bug, billing, access, or other), a priority (P1, P2, P3), a queue, and a short customer reply.",
                "",
                HOW_IT_RUNS,
                "",
                "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
                "",
                "Bugs go to engineering, billing goes to billing, and the rest go to support. P1 means work is blocked or money is wrong. P3 is a how-to. P2 is the rest.",
                "",
                'The customer reply must contain the ticket id, stay under 80 words, and say "refund" only when the ticket does.',
                "",
                "Sample ticket:",
                '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
            ]
        ),
    ),
)


WELCOME = "\n".join(
    [
        "Welcome to the AI Engineers Course.",
        "",
        "The best way to become a Forward Deployed Engineer (FDE) is to practice writing code with agents. Use any agentic coding tool you like, such as GitHub Copilot or Claude Code.",
        "",
        "Your assignment is below. When your code works, reply to this email with it attached as a single zip file.",
    ]
)

FIRST_STEPS = "\n".join(
    [
        "Since this is your first submission, here is the process step by step.",
        "",
        "With Claude Code:",
        "1. Install it: curl -fsSL https://claude.ai/install.sh | bash",
        "2. Make an empty folder for this assignment and start Claude Code in it: mkdir classify && cd classify && claude",
        "3. Paste the assignment above as your prompt, and add: \"Write main.py using only the Python standard library. Test it by piping the sample ticket into python3 main.py. When it works, create classify.zip containing main.py.\"",
        "4. Read what the agent writes and check the output it printed for the sample ticket.",
        "5. Check that classify.zip exists (if not, run: zip classify.zip main.py).",
        "6. Reply to this email with classify.zip attached.",
        "",
        "With GitHub Copilot:",
        "1. Install Visual Studio Code and the GitHub Copilot extension, then sign in to GitHub.",
        "2. Open an empty folder for this assignment (File > Open Folder).",
        "3. Open the Copilot Chat view and switch the mode to Agent.",
        "4. Paste the assignment above as your prompt, and add: \"Write main.py using only the Python standard library. Test it by piping the sample ticket into python3 main.py. When it works, create classify.zip containing main.py.\"",
        "5. Review the changes and check the output it printed for the sample ticket.",
        "6. Check that classify.zip exists (if not, run: zip classify.zip main.py).",
        "7. Reply to this email with classify.zip attached.",
        "",
        "The zip rules: one zip per email, 10 MB or less, with main.py at the top or inside a single folder.",
    ]
)

WHAT_HAPPENS_NEXT = "\n".join(
    [
        "What happens next:",
        "",
        "Your code is graded against tickets you have not seen. If you pass, you are promoted and receive the next assignment. If you fail, you get feedback on what to fix, and you can send a new zip on this thread.",
        "",
        "You have five graded tries per day (UTC).",
    ]
)


def _first_letter_body(level: Level) -> str:
    return "\n\n".join([WELCOME, level.body, FIRST_STEPS, WHAT_HAPPENS_NEXT])


@dataclass(frozen=True)
class Zip:
    filenames: tuple[str, ...]
    size_bytes: int


@dataclass(frozen=True)
class Letter:
    email: str
    message_id: str
    zip: Zip | None = None
    attachment_count: int | None = None


@dataclass
class StudentCard:
    email: str
    assignment_id: str = "triage"
    open_level: str | None = None
    in_flight: bool = False
    handled_message_ids: set[str] = field(default_factory=set)
    graded_tries_today: int = 0
    graded_day: date | None = None
    last_result: str | None = None
    finished: bool = False
    registered_at: str | None = None
    last_letter_at: str | None = None

    @property
    def level_index(self) -> int:
        for index, level in enumerate(LADDER):
            if level.name == self.open_level:
                return index
        return 0


@dataclass(frozen=True)
class Reply:
    email: str
    message_id: str
    body: str


MAX_ZIP_BYTES = 10 * 1024 * 1024
_FINDINGS_LIMIT = 8 * 1024
_ACCOUNT_ID = "000000000000"
_VPC_ID = "vpc-tutor"
_SUBNET_ID = "subnet-tutor"
_SECURITY_GROUP_ID = "sg-tutor"


class Model(Protocol):
    def note(self, level: str, result: str) -> str: ...


class _RoomAdapter:
    def __init__(self, room: Room, cards: dict[str, StudentCard], pull=None) -> None:
        self._room = room
        self._cards = cards
        self._pull = pull
        self.findings: dict[str, str] = {}

    def grade(self, submission: Submission) -> RoomResult:
        card = self._cards[submission.email]
        card.in_flight = True
        try:
            if self._pull is not None:
                self._pull()
            raw = self._room.grade(submission)
        finally:
            card.in_flight = False
        if isinstance(raw, RoomResult):
            return raw
        self.findings[submission.message_id] = raw.findings
        return raw.result


def _attachment_count(letter: Letter) -> int:
    if letter.attachment_count is not None:
        return letter.attachment_count
    if letter.zip is None:
        return 0
    return 1


def _path_parts(name: str) -> list[str]:
    return [part for part in name.split("/") if part]


def _main_py_is_at_the_top_or_in_one_folder(filenames: tuple[str, ...]) -> bool:
    paths = [path for path in (_path_parts(name) for name in filenames) if path]
    if ["main.py"] in paths:
        return True
    top_levels = {path[0] for path in paths}
    if len(top_levels) != 1:
        return False
    folder = next(iter(top_levels))
    return [folder, "main.py"] in paths


def _asks_for_a_single_zip(letter: Letter) -> bool:
    if _attachment_count(letter) > 1:
        return True
    archive = letter.zip
    if archive is None:
        return False
    if archive.size_bytes > MAX_ZIP_BYTES:
        return True
    return not _main_py_is_at_the_top_or_in_one_folder(archive.filenames)


def _open_level_body(card: StudentCard) -> str:
    for level in LADDER:
        if level.name == card.open_level:
            return level.body
    return LADDER[0].body


def _level_after(name: str) -> Level | None:
    for index, level in enumerate(LADDER):
        if level.name == name:
            if index + 1 < len(LADDER):
                return LADDER[index + 1]
            return None
    return None


def _is_accepted_zip(letter: Letter) -> bool:
    return letter.zip is not None and not _asks_for_a_single_zip(letter)


def _message_already_handled(cards: dict[str, StudentCard], message_id: str) -> bool:
    return any(message_id in card.handled_message_ids for card in cards.values())


def _quota_for(card: StudentCard, today: date) -> Quota:
    if card.graded_day is None:
        if card.graded_tries_today:
            return Quota(today, card.graded_tries_today)
        return Quota()
    return Quota(card.graded_day, card.graded_tries_today)


def _truncate_findings(findings: str) -> str:
    raw = findings.encode("utf-8")
    if len(raw) <= _FINDINGS_LIMIT:
        return findings
    return raw[:_FINDINGS_LIMIT].decode("utf-8", errors="ignore")


def _remember_quota(card: StudentCard, quota: Quota) -> None:
    card.graded_tries_today = quota.graded_attempts
    if quota.attempt_day is not None:
        card.graded_day = quota.attempt_day


def _reply_for_known_student(card: StudentCard, letter: Letter) -> str:
    if card.finished:
        return "The ladder is finished."
    if _asks_for_a_single_zip(letter):
        return "Send a single zip."
    return _open_level_body(card)


_SEND_AGAIN = "Send that zip again after the result."


def _bodies_for_results(
    submissions: list[tuple[Letter, str]],
    cards: dict[str, StudentCard],
    quotas: dict[str, Quota],
    result,
    adapter: _RoomAdapter,
    model: Model | None,
) -> dict[str, str]:
    by_id = {item.message_id: item for item in result.items}
    bodies: dict[str, str] = {}
    for letter, level_name in submissions:
        item = by_id[letter.message_id]
        card = cards[letter.email]
        _remember_quota(card, quotas[letter.email])
        if item.outcome is Outcome.PASS:
            card.last_result = "pass"
            note = model.note(level_name, "pass") if model is not None else ""
            nxt = _level_after(level_name)
            if nxt is None:
                card.finished = True
                trailer = "The ladder is finished."
            else:
                card.open_level = nxt.name
                trailer = nxt.body
            parts = ["Pass", note, trailer]
            bodies[letter.message_id] = "\n\n".join(part for part in parts if part)
        elif item.outcome is Outcome.FAIL:
            card.last_result = "fail"
            note = model.note(level_name, "fail") if model is not None else ""
            parts = [
                "Fail",
                note,
                _truncate_findings(adapter.findings.get(letter.message_id, "")),
            ]
            bodies[letter.message_id] = "\n\n".join(part for part in parts if part)
        elif item.outcome is Outcome.NOT_GRADED:
            card.last_result = "not graded"
            bodies[letter.message_id] = "Not graded"
        elif item.outcome is Outcome.CAPPED:
            card.last_result = "cap hit"
            bodies[letter.message_id] = "Cap hit"
    return bodies


def receive(
    letters: Sequence[Letter],
    cards: dict[str, StudentCard],
    *,
    door: Door,
    room: Room,
    model: Model | None = None,
    today: date | None = None,
    arrive: Callable[[], Sequence[Letter]] | None = None,
) -> list[Reply]:
    today = today or datetime.now(timezone.utc).date()
    ordered: list[Letter] = []
    bodies: dict[str, str] = {}
    submissions: list[tuple[Letter, str]] = []
    claimed: set[str] = set()
    seen: set[str] = set()
    quotas: dict[str, Quota] = {}

    def take(letter: Letter, *, can_join: bool) -> Submission | None:
        if letter.message_id in seen or _message_already_handled(cards, letter.message_id):
            return None
        seen.add(letter.message_id)
        card = cards.get(letter.email)
        if (
            card is not None
            and not card.finished
            and _is_accepted_zip(letter)
            and letter.email in claimed
        ):
            card.handled_message_ids.add(letter.message_id)
            ordered.append(letter)
            bodies[letter.message_id] = _SEND_AGAIN
            return None
        if not can_join:
            return None
        if card is None:
            card = StudentCard(email=letter.email)
            cards[letter.email] = card
            level = LADDER[0]
            card.handled_message_ids.add(letter.message_id)
            card.open_level = level.name
            ordered.append(letter)
            bodies[letter.message_id] = _first_letter_body(level)
            return None
        if not card.finished and _is_accepted_zip(letter):
            card.handled_message_ids.add(letter.message_id)
            ordered.append(letter)
            claimed.add(letter.email)
            submissions.append((letter, card.open_level or LADDER[0].name))
            quotas.setdefault(letter.email, _quota_for(card, today))
            return Submission(letter.email, letter.message_id)
        card.handled_message_ids.add(letter.message_id)
        ordered.append(letter)
        bodies[letter.message_id] = _reply_for_known_student(card, letter)
        return None

    for letter in letters:
        take(letter, can_join=True)

    def batch_arrive() -> list[Submission]:
        if arrive is None:
            return []
        delivered: list[Submission] = []
        for letter in arrive():
            submission = take(letter, can_join=True)
            if submission is not None:
                delivered.append(submission)
        return delivered

    def pull_while_grading() -> None:
        if arrive is None:
            return
        for letter in arrive():
            take(letter, can_join=False)

    if submissions or arrive is not None:
        adapter = _RoomAdapter(room, cards, pull_while_grading if arrive is not None else None)
        waiting = [Submission(letter.email, letter.message_id) for letter, _name in submissions]
        result = run_batch(
            waiting,
            quotas,
            door=door,
            room=adapter,
            today=today,
            account_id=_ACCOUNT_ID,
            vpc_id=_VPC_ID,
            subnet_id=_SUBNET_ID,
            security_group_id=_SECURITY_GROUP_ID,
            arrive=batch_arrive if arrive is not None else None,
        )
        bodies.update(
            _bodies_for_results(submissions, cards, quotas, result, adapter, model)
        )
    return [Reply(letter.email, letter.message_id, bodies[letter.message_id]) for letter in ordered]
