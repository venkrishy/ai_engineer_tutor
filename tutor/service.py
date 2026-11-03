"""Handle one saved letter against the stored student cards.

A letter is claimed by its message id first, so the same letter is replied to
once. If the send fails, the claim is released and the letter can be tried
again.
"""

from __future__ import annotations

import email

from tutor.mail import _addressed_to_tutor, deliver, sender_of
from tutor.store import Store


def handle(raw: bytes, *, store: Store, mail, door, room, ses, model=None, today=None) -> str:
    incoming = email.message_from_bytes(raw)
    if not _addressed_to_tutor(incoming):
        return "ignored"
    sender = sender_of(incoming)
    message_id = (incoming["Message-ID"] or "").strip()
    if not message_id:
        return "ignored"
    if not store.claim(message_id, sender):
        return "duplicate"
    card = store.load_card(sender)
    cards = {sender: card} if card is not None else {}
    try:
        body = deliver(
            raw, cards, mail=mail, door=door, room=room, ses=ses, model=model, today=today
        )
    except Exception:
        store.release(message_id)
        raise
    if sender in cards:
        store.save_card(cards[sender])
    store.record_event(sender, message_id, "letter", incoming.get("Subject") or "")
    if body is not None:
        store.record_event(sender, message_id, "reply", body)
    return "handled"
