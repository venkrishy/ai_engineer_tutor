"""Turn a letter into one reply and the updated student card.

A first letter creates the student and replies with the first assignment.
A zip on that letter is ignored. A later letter that is not a submission
replies with the open assignment, asks for a single zip, or tells a
finished student the ladder is finished. Nothing is graded, so the door
and the room stay shut.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tutor.grading import Door, Room

@dataclass(frozen=True)
class Assignment:
    name: str
    instructions: str

    @property
    def body(self) -> str:
        return f"{self.name}\n\n{self.instructions}"


LADDER = (
    Assignment(
        name="Classify",
        instructions="\n".join(
            [
                "Read one ticket as JSON and print one JSON object with the ticket id and a label: bug, billing, access, or other.",
                "",
                "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
                "",
                "Sample ticket:",
                '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
            ]
        ),
    ),
)


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
    open_assignment: str | None = None
    in_flight: bool = False
    handled_message_ids: set[str] = field(default_factory=set)
    graded_tries_today: int = 0
    finished: bool = False


@dataclass(frozen=True)
class Reply:
    email: str
    message_id: str
    body: str


MAX_ZIP_BYTES = 10 * 1024 * 1024


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


def _open_assignment_body(card: StudentCard) -> str:
    for assignment in LADDER:
        if assignment.name == card.open_assignment:
            return assignment.body
    return LADDER[0].body


def _reply_for_known_student(card: StudentCard, letter: Letter) -> str:
    if card.finished:
        return "The ladder is finished."
    if _asks_for_a_single_zip(letter):
        return "Send a single zip."
    return _open_assignment_body(card)


def receive(
    letters: Sequence[Letter],
    cards: dict[str, StudentCard],
    *,
    door: Door,
    room: Room,
) -> list[Reply]:
    del door, room
    replies: list[Reply] = []
    for letter in letters:
        if any(
            letter.message_id in existing.handled_message_ids for existing in cards.values()
        ):
            continue
        card = cards.get(letter.email)
        if card is None:
            card = StudentCard(email=letter.email)
            cards[letter.email] = card
            assignment = LADDER[0]
            card.handled_message_ids.add(letter.message_id)
            card.open_assignment = assignment.name
            replies.append(Reply(letter.email, letter.message_id, assignment.body))
            continue
        card.handled_message_ids.add(letter.message_id)
        replies.append(
            Reply(letter.email, letter.message_id, _reply_for_known_student(card, letter))
        )
    return replies
