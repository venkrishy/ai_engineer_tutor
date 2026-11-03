import email
import email.policy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fakes import plain_part
from test_mail import TESTER, MailStandIn, raw_letter, verified_for
from test_clerk import DoorThatMustStayShut, RoomThatMustStayShut

from tutor.clerk import LADDER, Level, StudentCard
from tutor.mail import deliver
from tutor.render import progress_for, render_reply, status_for, to_html

TODAY = date(2026, 11, 2)
TRIAGE = (
    Level("Classify", "x", "triage", assignment_name="Triage tickets"),
    Level("Route", "x", "triage", assignment_name="Triage tickets"),
    Level("Reply", "x", "triage", assignment_name="Triage tickets"),
)


class RenderTest(unittest.TestCase):
    def test_bold_and_code_become_tags(self):
        self.assertIn("<strong>Hi</strong>", to_html("**Hi** there"))
        self.assertIn(">main.py</code>", to_html("Use `main.py` now"))

    def test_text_is_escaped(self):
        page = to_html("a <script>alert(1)</script> & b")

        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_a_fenced_block_keeps_its_lines_and_is_not_formatted(self):
        page = to_html("Before\n\n```\nline **one**\n  line two\n```\n\nAfter")

        self.assertIn("<pre", page)
        self.assertIn("line **one**\n  line two", page)
        self.assertEqual(page.count("<p "), 2)

    def test_numbered_and_bulleted_lists(self):
        page = to_html("1. one\n2. two\n\n- a\n- b")

        self.assertEqual(page.count("<ol"), 1)
        self.assertEqual(page.count("<ul"), 1)
        self.assertEqual(page.count("<li"), 4)

    def test_a_line_that_is_only_dashes_is_a_rule(self):
        self.assertIn("<hr", to_html("a\n\n---\n\nb"))

    def test_the_status_says_level_and_tries_left(self):
        card = StudentCard(email="a@example.com", open_level="Route", graded_tries_today=2, graded_day=TODAY)

        self.assertEqual(
            status_for(card, TRIAGE, TODAY),
            "Your status: Triage tickets, Level 2 of 3 (Route). Levels cleared: 1. Graded tries left today: 3 of 5.",
        )

    def test_tries_from_another_day_do_not_count(self):
        card = StudentCard(email="a@example.com", open_level="Classify", graded_tries_today=5, graded_day=date(2026, 11, 1))

        self.assertIn("Graded tries left today: 5 of 5", status_for(card, TRIAGE, TODAY))

    def test_a_finished_student_is_told_so(self):
        card = StudentCard(email="a@example.com", open_level="Reply", finished=True)

        self.assertIn("cleared every level", status_for(card, TRIAGE, TODAY))

    def test_the_reply_is_plain_text_first_with_the_status_after_it(self):
        text, page = render_reply("Pass\n\nWell done.", "Your status: x")

        self.assertEqual(text.splitlines()[0], "Pass")
        self.assertTrue(text.endswith("Your status: x"))
        self.assertIn("<strong>Your status:</strong>", page)
        self.assertIn("AI Engineers Course", page)

    def test_a_delivered_reply_has_a_plain_and_an_html_part(self):
        mail = MailStandIn()
        deliver(
            raw_letter(TESTER, "<m1@x>"),
            {},
            mail=mail,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            ses=verified_for(TESTER),
            today=TODAY,
        )

        message = email.message_from_bytes(mail.sent[0], policy=email.policy.default)

        self.assertEqual(message.get_content_type(), "multipart/alternative")
        self.assertIn("Welcome to the AI Engineers Course.", plain_part(message))
        self.assertIn("Your status:", message.get_body(("plain",)).get_content())
        self.assertIn("<strong>Welcome to the AI Engineers Course.</strong>", message.get_body(("html",)).get_content())


if __name__ == "__main__":
    unittest.main()


class HeadingTest(unittest.TestCase):
    def test_a_line_starting_with_two_hashes_is_a_heading(self):
        page = to_html("## Classify tickets\n\nBody")

        self.assertIn("<h2", page)
        self.assertIn("Classify tickets</h2>", page)
        self.assertEqual(page.count("<p "), 1)


class LinkAndProgressTest(unittest.TestCase):
    def test_a_markdown_link_becomes_an_anchor(self):
        page = to_html("Open [the page](https://example.com/a?x=1&y=2) now")

        self.assertIn('<a href="https://example.com/a?x=1&amp;y=2"', page)
        self.assertIn(">the page</a>", page)

    def test_only_https_links_become_anchors(self):
        self.assertNotIn("<a ", to_html("[x](javascript:alert(1))"))

    def test_progress_counts_cleared_levels(self):
        card = StudentCard(email="a@example.com", open_level="Route")

        self.assertEqual(progress_for(card, TRIAGE), (1, 3))
        card.finished = True
        self.assertEqual(progress_for(card, TRIAGE), (3, 3))
        self.assertIsNone(progress_for(None, TRIAGE))

    def test_the_reply_shows_the_progress_in_both_parts(self):
        text, page = render_reply("Pass", "Your status: x", (1, 3))

        self.assertTrue(text.endswith("Progress: [#--]"))
        self.assertIn("Level 2 of 3", page)
        self.assertEqual(page.count("<td style=\"height:8px"), 3)
