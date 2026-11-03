import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_catalog import fake_tickets

from tutor.catalog import LevelAssets, match_expected
from tutor.judge import Run, judge


def assets():
    return LevelAssets(fake_tickets("02-route"), match_expected)


def answer_for(ticket, **changes):
    return json.dumps(dict(ticket["expected"], id=ticket["input"]["id"], **changes))


class JudgeTest(unittest.TestCase):
    def runner(self, wrong=(), **overrides):
        by_id = {t["input"]["id"]: t for t in assets().tickets}

        def run_one(ticket_input):
            ticket = by_id[ticket_input["id"]]
            if ticket_input["id"] in overrides:
                return overrides[ticket_input["id"]]
            if ticket_input["id"] in wrong:
                return Run(answer_for(ticket, label="other", queue="support", priority="P3"))
            return Run(answer_for(ticket))

        return run_one

    def test_five_of_five_passes(self):
        self.assertTrue(judge(assets(), self.runner()).passed)

    def test_four_of_five_passes(self):
        self.assertTrue(judge(assets(), self.runner(wrong=("T-900",))).passed)

    def test_three_of_five_fails_and_says_which_tickets(self):
        verdict = judge(assets(), self.runner(wrong=("T-900", "T-901")))

        self.assertFalse(verdict.passed)
        self.assertIn("3 of 5 tickets passed; 4 are needed.", verdict.findings)
        self.assertIn("Ticket 1 (Locked out):", verdict.findings)
        self.assertIn("Ticket 2 (Please refund me):", verdict.findings)

    def test_findings_do_not_reveal_the_answer(self):
        verdict = judge(assets(), self.runner(wrong=("T-900", "T-901")))

        self.assertNotIn("access", verdict.findings)
        self.assertNotIn("P1", verdict.findings)

    def test_a_crash_is_a_failed_ticket_with_the_tail_of_the_error(self):
        crashed = {t["input"]["id"]: Run("", "Traceback...\nKeyError: 'subject'", 1) for t in assets().tickets}

        verdict = judge(assets(), self.runner(**crashed))

        self.assertFalse(verdict.passed)
        self.assertIn("the program crashed: Traceback", verdict.findings)

    def test_output_that_is_not_one_json_object_fails_the_ticket(self):
        noisy = {t["input"]["id"]: Run("debug line\n" + answer_for(t)) for t in assets().tickets}

        verdict = judge(assets(), self.runner(**noisy))

        self.assertIn("the output is not exactly one JSON object", verdict.findings)

    def test_a_timeout_fails_the_ticket(self):
        slow = {t["input"]["id"]: Run("", timed_out=True) for t in assets().tickets}

        verdict = judge(assets(), self.runner(**slow))

        self.assertIn("the program took too long", verdict.findings)

    def test_the_program_is_only_given_the_input(self):
        seen = []

        def run_one(ticket_input):
            seen.append(ticket_input)
            return Run("{}")

        judge(assets(), run_one)

        self.assertTrue(all(set(item) == {"id", "subject", "body"} for item in seen))


if __name__ == "__main__":
    unittest.main()
