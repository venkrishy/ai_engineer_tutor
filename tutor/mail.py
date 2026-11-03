"""Turn one raw letter into one reply on that same thread.

The reply body comes from the clerk. The letter is addressed to the tutor,
and the reply goes to the address the letter came from.
"""

from __future__ import annotations

import email
import io
import zipfile
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr

from tutor.clerk import Letter, Zip, receive

TUTOR_ADDRESS = "tutor@theaiguru.dev"
REGION = "us-east-1"
CONFIGURATION_SET = "tutor"
MAILBOX_SIMULATOR = frozenset(
    {
        "success@simulator.amazonses.com",
        "bounce@simulator.amazonses.com",
        "complaint@simulator.amazonses.com",
        "suppressionlist@simulator.amazonses.com",
        "ooto@simulator.amazonses.com",
    }
)


@dataclass(frozen=True)
class SesSending:
    production_access: bool
    verified: frozenset[str]


class SendRefused(Exception):
    """The reply stays unsent. The letter is left unhandled."""


def _zip_for(incoming) -> tuple[Zip | None, int | None]:
    attachments = [
        part
        for part in incoming.walk()
        if part.get_content_disposition() == "attachment"
    ]
    if not attachments:
        return None, None
    if len(attachments) != 1:
        return None, len(attachments)
    payload = attachments[0].get_payload(decode=True) or b""
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        return None, 1
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        filenames = tuple(archive.namelist())
    return Zip(filenames, len(payload)), None


def sender_of(incoming) -> str:
    return parseaddr(incoming.get("From", ""))[1].strip().lower()


def _addressed_to_tutor(incoming) -> bool:
    recipients = {
        addr.strip().lower()
        for _name, addr in getaddresses(incoming.get_all("To", []))
        if addr
    }
    return TUTOR_ADDRESS in recipients


class SesMail:
    def __init__(self, client) -> None:
        self._client = client

    def send(self, raw: bytes) -> None:
        self._client.send_email(
            FromEmailAddress=TUTOR_ADDRESS,
            ConfigurationSetName=CONFIGURATION_SET,
            Content={"Raw": {"Data": raw}},
        )


def ses_sending(client) -> SesSending:
    status = client.get_account()
    verified: list[str] = []
    token = None
    while True:
        page = client.list_email_identities(**({"NextToken": token} if token else {}))
        verified.extend(
            item["IdentityName"]
            for item in page.get("EmailIdentities", [])
            if item.get("VerificationStatus") == "SUCCESS"
        )
        token = page.get("NextToken")
        if not token:
            break
    return SesSending(
        production_access=bool(status.get("ProductionAccessEnabled")),
        verified=frozenset(verified),
    )


def ses_mail(factory=None) -> SesMail:
    if factory is None:
        import boto3

        factory = boto3.client
    return SesMail(factory("sesv2", region_name=REGION))


def deliver(raw: bytes, cards, *, mail, door, room, ses: SesSending, model=None, today=None):
    incoming = email.message_from_bytes(raw)
    if not _addressed_to_tutor(incoming):
        return None
    sender = sender_of(incoming)
    verified = {item.strip().lower() for item in ses.verified}
    domain = sender.rsplit("@", 1)[-1]
    allowed = (
        ses.production_access
        or sender in verified
        or sender in MAILBOX_SIMULATOR
        or domain in verified
    )
    if not allowed:
        raise SendRefused(sender)
    message_id = incoming["Message-ID"].strip()
    archive, attachment_count = _zip_for(incoming)
    replies = receive(
        [Letter(sender, message_id, archive, attachment_count)],
        cards,
        door=door,
        room=room,
        model=model,
        today=today,
    )
    if not replies:
        return None
    reply = replies[0]
    outbound = EmailMessage()
    outbound["From"] = TUTOR_ADDRESS
    subject = incoming.get("Subject") or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}" if subject else "Re:"
    card = cards.get(sender)
    tag = f"[{card.assignment_id}]" if card is not None else ""
    outbound["Subject"] = f"{subject} {tag}" if tag and tag not in subject else subject
    outbound["To"] = reply.email
    outbound["In-Reply-To"] = message_id
    outbound["References"] = message_id
    outbound.set_content(reply.body)
    mail.send(outbound.as_bytes())
    return reply.body


def answer(stored, cards, *, mail, door, room, ses, model=None, today=None):
    for raw in stored:
        deliver(raw, cards, mail=mail, door=door, room=room, ses=ses, model=model, today=today)
