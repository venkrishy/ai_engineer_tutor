import email
import email.policy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fakes import MemoryItems
from test_clerk import FIRST_LETTER_BODY, DoorThatMustStayShut, QueuedRoom, RoomThatMustStayShut
from test_mail import MailStandIn, raw_letter, verified_for, TESTER

from tutor.clerk import StudentCard
from tutor.grading import DAILY_GRADED_ATTEMPT_CAP, RoomResult
from tutor.mail import SendRefused, SesSending
from tutor.rooms import NullDoor
from tutor.service import GLOBAL_DAILY_CAP, handle
from tutor.store import Store


class FailingMail:
    def send(self, raw):
        raise SendRefused("x")


def body_of(raw):
    return email.message_from_bytes(raw, policy=email.policy.default).get_content()


def trusted(raw, *, spam="PASS", virus="PASS", auth="dmarc=pass header.from=gmail.com;"):
    headers = (
        f"X-SES-Spam-Verdict: {spam}\r\n"
        f"X-SES-Virus-Verdict: {virus}\r\n"
        f"Authentication-Results: amazonses.com; spf=pass; {auth}\r\n"
    )
    return headers.encode() + raw


def run(raw, store, mail, ses=None, room=None, door=None, **verdicts):
    return handle(
        trusted(raw, **verdicts),
        store=store,
        mail=mail,
        door=door or DoorThatMustStayShut(),
        room=room or RoomThatMustStayShut(),
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

    def test_a_letter_that_failed_the_spam_check_gets_no_reply(self):
        result = run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail, spam="FAIL")

        self.assertEqual(result, "untrusted")
        self.assertEqual(self.mail.sent, [])
        self.assertIsNone(self.store.load_card(TESTER))

    def test_a_letter_that_failed_the_virus_check_gets_no_reply(self):
        result = run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail, virus="FAIL")

        self.assertEqual(result, "untrusted")

    def test_a_letter_whose_sender_cannot_be_confirmed_gets_no_reply(self):
        result = run(
            raw_letter(TESTER, "<m1@x>"), self.store, self.mail, auth="dmarc=fail header.from=gmail.com;"
        )

        self.assertEqual(result, "untrusted")
        self.assertEqual(self.mail.sent, [])

    def test_a_dkim_signature_from_the_senders_own_domain_is_enough(self):
        result = run(
            raw_letter(TESTER, "<m1@x>"),
            self.store,
            self.mail,
            auth="dkim=pass header.i=@gmail.com; dmarc=none header.from=gmail.com;",
        )

        self.assertEqual(result, "handled")

    def test_a_dkim_signature_from_another_domain_is_not_enough(self):
        result = run(
            raw_letter(TESTER, "<m1@x>"),
            self.store,
            self.mail,
            auth="dkim=pass header.i=@evil.example; dmarc=none header.from=gmail.com;",
        )

        self.assertEqual(result, "untrusted")

    def test_a_paused_registration_welcomes_no_new_student(self):
        self.store.set_setting("paused", True)

        result = run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail)

        self.assertEqual(result, "paused")
        self.assertEqual(self.mail.sent, [])
        self.assertIsNone(self.store.load_card(TESTER))

    def test_a_paused_registration_still_answers_a_known_student(self):
        run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail)
        self.store.set_setting("paused", True)

        result = run(raw_letter(TESTER, "<m2@x>"), self.store, self.mail)

        self.assertEqual(result, "handled")
        self.assertEqual(len(self.mail.sent), 2)

    def test_a_graded_try_counts_toward_the_global_cap(self):
        run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail)
        zipped = raw_letter(TESTER, "<m2@x>", files=[("main.py", "print(1)")])

        run(zipped, self.store, self.mail, room=QueuedRoom([RoomResult.PASS]), door=NullDoor())

        self.assertEqual(self.store.global_tries(date(2026, 11, 2)), 1)

    def test_at_the_global_cap_a_submission_is_cap_hit_and_the_students_tries_are_kept(self):
        run(raw_letter(TESTER, "<m1@x>"), self.store, self.mail)
        self.store.add_global_tries(date(2026, 11, 2), GLOBAL_DAILY_CAP)
        zipped = raw_letter(TESTER, "<m2@x>", files=[("main.py", "print(1)")])

        run(zipped, self.store, self.mail, room=RoomThatMustStayShut(), door=NullDoor())

        reply = body_of(self.mail.sent[-1])
        self.assertEqual(reply.splitlines()[0], "Cap hit")
        card = self.store.load_card(TESTER)
        self.assertEqual(card.graded_tries_today, 0)
        self.assertEqual(self.store.global_tries(date(2026, 11, 2)), GLOBAL_DAILY_CAP)

    def test_a_student_at_the_per_student_cap_is_cap_hit(self):
        card = StudentCard(
            email=TESTER,
            open_level="Classify",
            graded_tries_today=DAILY_GRADED_ATTEMPT_CAP,
            graded_day=date(2026, 11, 2),
        )
        self.store.save_card(card)
        zipped = raw_letter(TESTER, "<m2@x>", files=[("main.py", "print(1)")])

        run(zipped, self.store, self.mail, room=RoomThatMustStayShut(), door=NullDoor())

        self.assertEqual(body_of(self.mail.sent[-1]).splitlines()[0], "Cap hit")


if __name__ == "__main__":
    unittest.main()
