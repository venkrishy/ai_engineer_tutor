import email
import io
import unittest
import zipfile
from datetime import date
from email.message import EmailMessage

from test_clerk import (
    FIRST_LETTER_BODY,
    DoorThatMustStayShut,
    FixedNote,
    QueuedRoom,
    RecordingDoor,
    RoomThatMustStayShut,
)
from tutor.grading import RoomResult
from tutor.mail import SendRefused, SesSending, answer, deliver, ses_mail, ses_sending

TESTER = "venkrishy@gmail.com"
TUTOR = "tutor@theaiguru.dev"
FIRST_MESSAGE_ID = "<first-letter@mail.gmail.com>"


class MailStandIn:
    def __init__(self):
        self.sent = []

    def send(self, raw: bytes) -> None:
        self.sent.append(raw)


def raw_letter(sender, message_id, *, subject="Start", body="I am ready.", files=None):
    message = EmailMessage()
    message["From"] = f"Tester <{sender}>"
    message["To"] = f"Tutor <{TUTOR}>"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message.set_content(body)
    if files is not None:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, content in files:
                zipped.writestr(name, content)
        message.add_attachment(
            archive.getvalue(),
            maintype="application",
            subtype="zip",
            filename="work.zip",
        )
    return message.as_bytes()


def verified_for(*identities):
    return SesSending(production_access=False, verified=frozenset(identities))


class MailSeamTest(unittest.TestCase):
    def test_a_first_letter_from_the_testers_gmail_creates_the_student_and_replies_with_the_first_assignment(self):
        cards = {}
        mail = MailStandIn()
        deliver(
            raw_letter(TESTER, FIRST_MESSAGE_ID),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
        )

        self.assertEqual(list(cards), [TESTER])
        card = cards[TESTER]
        self.assertEqual(card.email, TESTER)
        self.assertEqual(card.open_assignment, "Classify")
        self.assertEqual(len(mail.sent), 1)
        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["From"])[1], TUTOR)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], TESTER)
        self.assertEqual(reply["In-Reply-To"], FIRST_MESSAGE_ID)
        self.assertEqual(reply["References"], FIRST_MESSAGE_ID)
        self.assertEqual(reply.get_content().splitlines(), FIRST_LETTER_BODY.splitlines())

    def test_a_stored_letter_from_the_testers_gmail_is_answered_and_a_setup_note_is_left_alone(self):
        cards = {}
        mail = MailStandIn()
        setup = EmailMessage()
        setup["From"] = "Amazon Web Services <no-reply-aws@amazon.com>"
        setup["To"] = "recipient@example.com"
        setup["Subject"] = "Amazon SES Setup Notification"
        setup.set_content("setup")
        answer(
            [setup.as_bytes(), raw_letter(TESTER, FIRST_MESSAGE_ID, subject="Registration")],
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
        )

        self.assertEqual(list(cards), [TESTER])
        self.assertEqual(len(mail.sent), 1)
        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], TESTER)
        self.assertEqual(reply["Subject"], "Re: Registration")
        self.assertEqual(reply["In-Reply-To"], FIRST_MESSAGE_ID)
        self.assertEqual(reply.get_content().splitlines(), FIRST_LETTER_BODY.splitlines())

    def test_an_accepted_zip_from_that_gmail_is_graded_and_the_reply_starts_with_the_result(self):
        cards = {}
        mail = MailStandIn()
        ses = verified_for(TESTER)
        deliver(
            raw_letter(TESTER, FIRST_MESSAGE_ID),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=ses,
        )
        room = QueuedRoom([RoomResult.PASS, RoomResult.FAIL, RoomResult.NOT_GRADED])
        mail.sent.clear()
        message_ids = (
            "<zip-pass@mail.gmail.com>",
            "<zip-fail@mail.gmail.com>",
            "<zip-open@mail.gmail.com>",
        )
        for message_id in message_ids:
            deliver(
                raw_letter(TESTER, message_id, files=(("main.py", b"print(1)\n"),)),
                cards,
                mail=mail,
                door=RecordingDoor(),
                room=room,
                model=FixedNote("The labels match the ticket."),
                today=date(2026, 11, 2),
                ses=ses,
            )

        first_lines = [
            email.message_from_bytes(raw, policy=email.policy.default).get_content().splitlines()[0]
            for raw in mail.sent
        ]
        self.assertEqual(first_lines, ["Pass", "Fail", "Not graded"])
        self.assertEqual(room.graded, list(message_ids))

    def test_the_reply_is_sent_to_the_address_the_letter_came_from(self):
        sender = "other.student@example.com"
        message_id = "<other-letter@mail.gmail.com>"
        cards = {}
        mail = MailStandIn()
        deliver(
            raw_letter(sender, message_id),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(sender),
        )

        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], sender)
        self.assertEqual(reply["In-Reply-To"], message_id)
        self.assertEqual(reply["References"], message_id)
        self.assertEqual(list(cards), [sender])

    def test_without_production_access_an_unverified_destination_is_not_sent(self):
        cards = {}
        mail = MailStandIn()
        raw = raw_letter(TESTER, FIRST_MESSAGE_ID)
        with self.assertRaises(SendRefused):
            deliver(
                raw,
                cards,
                mail=mail,
                door=DoorThatMustStayShut(),
                room=RoomThatMustStayShut(),
                ses=SesSending(production_access=False, verified=frozenset()),
            )

        self.assertEqual(mail.sent, [])
        self.assertEqual(cards, {})

        deliver(
            raw,
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
        )
        self.assertEqual(list(cards), [TESTER])
        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], TESTER)
        self.assertEqual(reply.get_content().splitlines(), FIRST_LETTER_BODY.splitlines())

    def test_without_production_access_the_mailbox_simulator_can_receive_the_reply(self):
        sender = "bounce@simulator.amazonses.com"
        cards = {}
        mail = MailStandIn()
        deliver(
            raw_letter(sender, "<simulator@mail.gmail.com>"),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=SesSending(production_access=False, verified=frozenset()),
        )

        self.assertEqual(len(mail.sent), 1)
        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], sender)

    def test_without_production_access_an_address_at_a_verified_domain_can_receive_the_reply(self):
        sender = "student@theaiguru.dev"
        cards = {}
        mail = MailStandIn()
        deliver(
            raw_letter(sender, "<domain-letter@mail.gmail.com>"),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=SesSending(production_access=False, verified=frozenset({"theaiguru.dev"})),
        )

        self.assertEqual(len(mail.sent), 1)
        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], sender)

    def test_with_production_access_an_unverified_destination_can_receive_the_reply(self):
        sender = "person@example.com"
        cards = {}
        mail = MailStandIn()
        deliver(
            raw_letter(sender, "<open-letter@mail.gmail.com>"),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=SesSending(production_access=True, verified=frozenset()),
        )

        self.assertEqual(len(mail.sent), 1)
        reply = email.message_from_bytes(mail.sent[0], policy=email.policy.default)
        self.assertEqual(email.utils.parseaddr(reply["To"])[1], sender)

    def test_the_same_letter_receives_one_reply(self):
        cards = {}
        mail = MailStandIn()
        raw = raw_letter(TESTER, FIRST_MESSAGE_ID)
        deliver(
            raw,
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
        )
        deliver(
            raw,
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
        )

        self.assertEqual(len(mail.sent), 1)
        self.assertEqual(list(cards), [TESTER])

    def test_the_ses_port_sends_the_raw_reply_from_the_tutor_in_us_east_1(self):
        class Client:
            def __init__(self):
                self.sent = []

            def send_email(self, **kwargs):
                self.sent.append(kwargs)

        client = Client()
        opened = {}

        def factory(service, *, region_name):
            opened["service"] = service
            opened["region"] = region_name
            return client

        ses_mail(factory).send(b"raw-reply")
        self.assertEqual(opened, {"service": "sesv2", "region": "us-east-1"})
        self.assertEqual(
            client.sent,
            [
                {
                    "FromEmailAddress": TUTOR,
                    "Content": {"Raw": {"Data": b"raw-reply"}},
                }
            ],
        )

    def test_ses_sending_uses_production_access_and_successful_identities(self):
        class Client:
            def get_account(self):
                return {"ProductionAccessEnabled": False}

            def list_email_identities(self, NextToken=None):
                if NextToken is None:
                    return {
                        "EmailIdentities": [
                            {
                                "IdentityName": TESTER,
                                "VerificationStatus": "SUCCESS",
                            },
                            {
                                "IdentityName": "pending@example.com",
                                "VerificationStatus": "PENDING",
                            },
                        ],
                        "NextToken": "page-2",
                    }
                return {
                    "EmailIdentities": [
                        {
                            "IdentityName": "theaiguru.dev",
                            "VerificationStatus": "SUCCESS",
                        },
                        {
                            "IdentityName": "failed@example.com",
                            "VerificationStatus": "FAILED",
                        },
                    ]
                }

        sending = ses_sending(Client())
        self.assertFalse(sending.production_access)
        self.assertEqual(sending.verified, frozenset({TESTER, "theaiguru.dev"}))

    def test_a_letter_that_is_not_addressed_to_the_tutor_gets_no_reply(self):
        message = EmailMessage()
        message["From"] = f"Tester <{TESTER}>"
        message["To"] = "other@example.com"
        message["Subject"] = "Start"
        message["Message-ID"] = "<elsewhere@mail.gmail.com>"
        message.set_content("hello")
        cards = {}
        mail = MailStandIn()
        deliver(
            message.as_bytes(),
            cards,
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
        )

        self.assertEqual(mail.sent, [])
        self.assertEqual(cards, {})


if __name__ == "__main__":
    unittest.main()
