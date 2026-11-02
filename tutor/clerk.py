"""Turn a letter into one reply and the updated student card.

A first letter creates the student. The reply is the first assignment on
the ladder. Nothing is graded, so the door and the room stay shut.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tutor.grading import Door, Room

FIRST_ASSIGNMENT = "Classify"

CLASSIFY_REPLY = "\n".join(
    [
        "Classify",
        "",
        "Read one ticket as JSON and print one JSON object with the ticket id and a label: bug, billing, access, or other.",
        "",
        "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
        "",
        "Sample ticket:",
        '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
    ]
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


@dataclass
class StudentCard:
    email: str
    open_assignment: str | None = None
    in_flight: bool = False
    handled_message_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Reply:
    email: str
    message_id: str
    body: str


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
        card = cards.get(letter.email)
        if card is None:
            card = StudentCard(email=letter.email)
            cards[letter.email] = card
        if letter.message_id in card.handled_message_ids:
            continue
        card.handled_message_ids.add(letter.message_id)
        card.open_assignment = FIRST_ASSIGNMENT
        replies.append(Reply(letter.email, letter.message_id, CLASSIFY_REPLY))
    return replies
