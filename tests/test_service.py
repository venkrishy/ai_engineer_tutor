import email
import email.policy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fakes import MemoryItems
from test_clerk import FIRST_LETTER_BODY, DoorThatMustStayShut, RoomThatMustStayShut
from test_mail import MailStandIn, raw_letter, verified_for, TESTER

from tutor.mail import SendRefused, SesSending
from tutor.service import handle
from tutor.store import Store


class FailingMail:
    def send(self, raw):
        raise SendRefused("x")


def body_of(raw):
    return email.message_from_bytes(raw, policy=email.policy.default).get_content()


def run(raw, store, mail, ses=None):
    return handle(
        raw,
        store=store,
        mail=mail,
        door=DoorThatMustStayShut(),
        room=RoomThatMustStayShut(),
        ses=ses or verified_for(TESTER),
        today=date(2026, 11, 2),
    )


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.items = MemoryItems()
        self.store = Store(self.items)
        self.mail = MailStandIn()

    def test_a_first_letter_is_saved_as_a_student_and_replied_to(self):
        result = run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail)

        self.assertEqual(result, "handled")
        self.assertEqual(len(self.mail.sent), 1)
        card = self.store.load_card(TESTER)
        self.assertEqual(card.open_level, "Classify")
        self.assertEqual(body_of(self.mail.sent[0]).rstrip(), FIRST_LETTER_BODY)

    def test_the_reply_subject_carries_the_assignment_id(self):
        run(raw_letter(TESTER, "<m1@x>", subject="Start"), self.store, self.mail)

        self.assertIn(b"Subject: Re: Start [triage]", self.mail.sent[0])

    def test_the_same_letter_twice_gets_one_reply(self):
        raw = raw_letter(TESTER, "<m1@x>")
        run(raw, self.store, self.mail)

        self.assertEqual(run(raw, self.store, self.mail), "duplicate")
        self.assertEqual(len(self.mail.sent), 1)

    def test_a_second_letter_finds_the_saved_student_and_gets_the_bare_assignment(self):
        run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail)
        run(raw_letter(TESTER, "<m2@x>"), self.store, self.mail)

        self.assertEqual(len(self.mail.sent), 2)
        self.assertNotIn("Welcome to the AI Engineers Course", body_of(self.mail.sent[1]))

    def test_a_refused_send_releases_the_letter_so_it_can_be_tried_again(self):
        raw = raw_letter(TESTER, "<m1@x>")
        with self.assertRaises(SendRefused):
            run(raw, self.store, FailingMail(), ses=SesSending(False, frozenset()))

        self.assertIsNone(self.store.load_card(TESTER))
        self.assertEqual(run(raw, self.store, self.mail), "handled")

    def test_history_holds_the_letter_and_the_reply(self):
        run(raw_letter(TESTER, "<m1@x>", subject="Start"), self.store, self.mail)

        kinds = [event["kind"] for event in self.store.events(TESTER)]
        self.assertEqual(sorted(kinds), ["letter", "reply"])

    def test_a_letter_not_addressed_to_the_tutor_is_ignored(self):
        raw = raw_letter(TESTER, "<m1@x>").replace(b"tutor@theaiguru.dev", b"other@theaiguru.dev")

        self.assertEqual(run(raw, self.store, self.mail), "ignored")
        self.assertEqual(self.mail.sent, [])


if __name__ == "__main__":
    unittest.main()
