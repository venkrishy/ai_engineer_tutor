"""Turn a letter into one reply and the updated student card.

A first letter creates the student and replies with a welcome, the first
level, and step-by-step instructions for a first submission.
A zip on that letter is ignored. A later accepted zip is one submission:
the tutor grades it through the batch and replies on the same thread.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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

PROMPT_INTRO = (
    "**Your prompt.** Copy everything in the box below and paste it into your coding tool "
    "exactly as it is. It holds the whole task, so you do not need to add anything."
)


@dataclass(frozen=True)
class Level:
    name: str
    instructions: str
    assignment: str = "triage"
    title: str = ""
    context: str = ""
    prompt: str = ""
    rubric: str = ""
    assignment_name: str = ""

    @property
    def body(self) -> str:
        if not self.prompt:
            return f"{self.name}\n\n{self.instructions}"
        parts = [f"## {self.title or self.name}"]
        if self.context:
            parts.append(self.context)
        parts.append(self.instructions)
        parts.append(f"{PROMPT_INTRO}\n\n```\n{self.prompt}\n```")
        return "\n\n".join(parts)


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
        "**Welcome to the AI Engineers Course.**",
        "",
        "The best way to become a Forward Deployed Engineer (FDE) is to practice building real things with AI coding agents. Use any agentic coding tool you like, such as Claude Code or GitHub Copilot.",
        "",
        "Here is how it works. I send you an assignment, one level at a time. You build it with your tool and email me the code as a single zip file. I grade it against tickets you have not seen, then reply on this same thread with the result and your next level.",
        "",
        "Your first level is below.",
    ]
)

FIRST_STEPS = "\n".join(
    [
        "**How to submit, step by step**",
        "",
        "With Claude Code:",
        "1. Install it: `curl -fsSL https://claude.ai/install.sh | bash`",
        "2. Make an empty folder and start Claude Code in it: `mkdir classify && cd classify && claude`",
        "3. Paste the whole prompt from the box above. Claude Code writes `main.py`, tests it, and creates `classify.zip` for you.",
        "4. Check that `classify.zip` is in the folder. If it is not, run `zip classify.zip main.py`.",
        "5. Reply to this email with `classify.zip` attached.",
        "",
        "With GitHub Copilot:",
        "1. Install Visual Studio Code and the GitHub Copilot extension, then sign in to GitHub.",
        "2. Open an empty folder (File > Open Folder).",
        "3. Open the Copilot Chat view and switch the mode to Agent.",
        "4. Paste the whole prompt from the box above. Copilot writes `main.py`, tests it, and creates `classify.zip` for you.",
        "5. Check that `classify.zip` is in the folder. If it is not, run `zip classify.zip main.py`.",
        "6. Reply to this email with `classify.zip` attached.",
        "",
        "**Zip rules:** one zip per email, 10 MB or less, with `main.py` at the top or inside a single folder.",
    ]
)

WHAT_HAPPENS_NEXT = "\n".join(
    [
        "**What happens next**",
        "",
        "Your code is graded against tickets you have not seen. If you pass, you move up a level and I send you the next one. If you fail, you get notes on what to fix, and you can send a new zip on this thread.",
        "",
        "You have five graded tries per day (UTC).",
    ]
)

DEFAULT_TEMPLATES = {"welcome": WELCOME, "steps": FIRST_STEPS, "next": WHAT_HAPPENS_NEXT}


def _first_letter_body(level: Level, templates: Mapping[str, str]) -> str:
    return "\n\n".join([templates["welcome"], level.body, templates["steps"], templates["next"]])


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

    def level_index(self, ladder: Sequence[Level] = LADDER) -> int:
        """Position of the open level among the levels of its assignment."""
        mine = [level for level in ladder if level.assignment == self.assignment_id]
        for index, level in enumerate(mine):
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
    def note(self, level: str, result: str, findings: str = "") -> str: ...


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


def _open_level_body(card: StudentCard, ladder: Sequence[Level]) -> str:
    for level in ladder:
        if level.assignment == card.assignment_id and level.name == card.open_level:
            return level.body
    return ladder[0].body


def _level_after(card: StudentCard, name: str, ladder: Sequence[Level]) -> Level | None:
    for index, level in enumerate(ladder):
        if level.assignment == card.assignment_id and level.name == name:
            if index + 1 < len(ladder):
                return ladder[index + 1]
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


def _reply_for_known_student(
    card: StudentCard, letter: Letter, ladder: Sequence[Level]
) -> str:
    if card.finished:
        return "The ladder is finished."
    if _asks_for_a_single_zip(letter):
        return "Send a single zip."
    return _open_level_body(card, ladder)


_SEND_AGAIN = "Send that zip again after the result."


def _bodies_for_results(
    submissions: list[tuple[Letter, str]],
    cards: dict[str, StudentCard],
    quotas: dict[str, Quota],
    result,
    adapter: _RoomAdapter,
    model: Model | None,
    ladder: Sequence[Level],
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
            nxt = _level_after(card, level_name, ladder)
            if nxt is None:
                card.finished = True
                trailer = "The ladder is finished."
            else:
                card.open_level = nxt.name
                card.assignment_id = nxt.assignment
                trailer = nxt.body
            parts = ["Pass", note, trailer]
            bodies[letter.message_id] = "\n\n".join(part for part in parts if part)
        elif item.outcome is Outcome.FAIL:
            card.last_result = "fail"
            findings = adapter.findings.get(letter.message_id, "")
            note = model.note(level_name, "fail", findings) if model is not None else ""
            parts = ["Fail", note, _truncate_findings(findings)]
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
    ladder: Sequence[Level] = LADDER,
    templates: Mapping[str, str] = DEFAULT_TEMPLATES,
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
            level = ladder[0]
            card.assignment_id = level.assignment
            card.handled_message_ids.add(letter.message_id)
            card.open_level = level.name
            ordered.append(letter)
            bodies[letter.message_id] = _first_letter_body(level, templates)
            return None
        if not card.finished and _is_accepted_zip(letter):
            card.handled_message_ids.add(letter.message_id)
            ordered.append(letter)
            claimed.add(letter.email)
            submissions.append((letter, card.open_level or ladder[0].name))
            quotas.setdefault(letter.email, _quota_for(card, today))
            return Submission(letter.email, letter.message_id)
        card.handled_message_ids.add(letter.message_id)
        ordered.append(letter)
        bodies[letter.message_id] = _reply_for_known_student(card, letter, ladder)
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
            _bodies_for_results(
                submissions, cards, quotas, result, adapter, model, ladder
            )
        )
    return [Reply(letter.email, letter.message_id, bodies[letter.message_id]) for letter in ordered]
