import unittest

from tutor.links import assignment_url, hints_url, level_folder


class LinksTest(unittest.TestCase):
    def test_a_level_folder_is_its_position_and_its_name(self):
        self.assertEqual(level_folder(1, "Classify"), "01-classify")
        self.assertEqual(level_folder(12, "Reply to Customer!"), "12-reply-to-customer")

    def test_both_pages_live_in_the_level_folder_on_github_pages(self):
        base = "https://venkrishy.github.io/ai_engineer_tutor/assignments/triage/levels/02-route/"

        self.assertEqual(assignment_url("triage", 2, "Route"), base + "assignment.html")
        self.assertEqual(hints_url("triage", 2, "Route"), base + "hints-and-help.html")
