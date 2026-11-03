"""Handle one saved letter against the stored student cards.

A letter is claimed by its message id first, so the same letter is replied to
once. If the send fails, the claim is released and the letter can be tried
again. Anyone who passes the sender checks is registered and welcomed.
"""

from __future__ import annotations

import email
import re
from datetime import date, datetime, timezone

from tutor.grading import DAILY_GRADED_ATTEMPT_CAP
from tutor.clerk import LADDER, StudentCard
from tutor.mail import _addressed_to_tutor, deliver, sender_of, zip_payload
from tutor.store import Store

GLOBAL_DAILY_CAP = 100


def is_trusted(incoming) -> bool:
    """SES passed the letter as clean mail from the address it claims."""
    if incoming.get("X-SES-Spam-Verdict", "").strip().upper() != "PASS":
        return False
    if incoming.get("X-SES-Virus-Verdict", "").strip().upper() != "PASS":
        return False
    results = " ".join((incoming.get("Authentication-Results") or "").lower().split())
    if "dmarc=pass" in results:
        return True
    domain = sender_of(incoming).rsplit("@", 1)[-1]
    signed = re.search(r"dkim=pass[^;]*header\.i=@?([\w.-]+)", results)
    return bool(signed) and (domain == signed.group(1) or domain.endswith("." + signed.group(1)))


def handle(
    raw: bytes,
    *,
    store: Store,
    mail,
    door,
    room=None,
    ses,
    model=None,
    today=None,
    ladder=LADDER,
    make_room=None,
) -> str:
    incoming = email.message_from_bytes(raw)
    if not _addressed_to_tutor(incoming):
        return "ignored"
    sender = sender_of(incoming)
    message_id = (incoming["Message-ID"] or "").strip()
    if not message_id:
        return "ignored"
    if not is_trusted(incoming):
        return "untrusted"
    today = today or datetime.now(timezone.utc).date()
    card = store.load_card(sender)
    if card is None and store.settings().get("paused"):
        return "paused"
    if not store.claim(message_id, sender):
        return "duplicate"
    cards = {sender: card} if card is not None else {}
    tries_before = _tries_on(card, today) if card is not None else 0
    held = _hold_at_global_cap(card, store, today)
    if make_room is not None:
        payload = zip_payload(incoming)
        room = make_room(cards, {message_id: payload} if payload is not None else {})
    try:
        body = deliver(
            raw,
            cards,
            mail=mail,
            door=door,
            room=room,
            ses=ses,
            model=model,
            today=today,
            ladder=ladder,
        )
    except Exception:
        store.release(message_id)
        raise
    if sender in cards:
        _count_graded_tries(cards[sender], tries_before, held, store, today)
        store.save_card(cards[sender], ladder)
    store.record_event(sender, message_id, "letter", incoming.get("Subject") or "")
    if body is not None:
        store.record_event(sender, message_id, "reply", body)
    return "handled"


def _tries_on(card: StudentCard, today: date) -> int:
    return card.graded_tries_today if card.graded_day == today else 0


def _hold_at_global_cap(card, store: Store, today: date):
    """When 100 tries are used today, every student looks capped for this letter."""
    if card is None or store.global_tries(today) < GLOBAL_DAILY_CAP:
        return None
    held = (card.graded_tries_today, card.graded_day)
    card.graded_tries_today = DAILY_GRADED_ATTEMPT_CAP
    card.graded_day = today
    return held


def _count_graded_tries(
    card: StudentCard, tries_before: int, held, store: Store, today: date
) -> None:
    if held is not None:
        card.graded_tries_today, card.graded_day = held
        return
    spent = _tries_on(card, today) - tries_before
    if spent > 0:
        store.add_global_tries(today, spent)
