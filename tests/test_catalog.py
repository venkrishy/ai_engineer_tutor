import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fakes import MemoryBlobs, MemoryItems
from test_clerk import CLASSIFY_BODY
from tutor.clerk import level_email

from tutor.catalog import (
    BundleError,
    assignments,
    load_assets,
    load_ladder,
    parse_bundle,
    save_bundle,
)

TRIAGE = Path(__file__).parent.parent / "assignments" / "triage"


def fake_tickets(level_folder: str) -> list[dict]:
    """Five made-up tickets. The real ones are hidden and not in this repository."""
    rows = [
        ("T-900", "Locked out", "I cannot sign in to my account.", "access", "P1", "support"),
        ("T-901", "Please refund me", "Refund the duplicate charge on my invoice.", "billing", "P1", "billing"),
        ("T-902", "Chart is wrong", "The chart shows the wrong colors. The product is broken.", "bug", "P2", "engineering"),
        ("T-903", "Change language", "Where do I change the interface language?", "other", "P3", "support"),
        ("T-904", "Invoice copy", "Send me a copy of the February invoice.", "billing", "P2", "billing"),
    ]
    fields = ("label",) if level_folder.startswith("01") else ("label", "priority", "queue")
    tickets = []
    for id_, subject, body, *answer in rows:
        expected = {k: v for k, v in zip(("label", "priority", "queue"), answer) if k in fields}
        ticket = {"input": {"id": id_, "subject": subject, "body": body}, "expected": expected}
        if level_folder.startswith("03"):
            ticket["good"] = dict(expected, id=id_, reply=f"Thanks. We are on {id_}.")
        tickets.append(ticket)
    return tickets


def zip_of(folder: Path, drop=(), add=None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(folder.rglob("*")):
            name = path.relative_to(folder).as_posix()
            if path.is_file() and name not in drop and not name.endswith("tickets.json"):
                archive.writestr(name, path.read_bytes())
        for level in sorted((folder / "levels").iterdir()):
            name = f"levels/{level.name}/tickets.json"
            if name not in drop and name not in (add or {}):
                archive.writestr(name, json.dumps(fake_tickets(level.name)))
        for name, content in (add or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.items = MemoryItems()
        self.blobs = MemoryBlobs()

    def upload(self, data=None):
        return save_bundle(self.items, self.blobs, parse_bundle(data or zip_of(TRIAGE)))

    def test_the_triage_bundle_makes_a_ladder_of_classify_route_reply(self):
        self.upload()

        ladder = load_ladder(self.items)

        self.assertEqual([level.name for level in ladder], ["Classify", "Route", "Reply"])
        self.assertEqual({level.assignment for level in ladder}, {"triage"})

    def test_the_first_level_email_carries_the_title_the_story_and_the_page_links_but_not_the_prompt(self):
        self.upload()
        ladder = load_ladder(self.items)

        body = level_email(ladder[0], ladder)

        self.assertTrue(body.startswith("## Classify incoming support tickets"))
        self.assertIn("Imagine you work for a large enterprise software company", body)
        self.assertIn("assignments/triage/levels/01-classify/assignment.html", body)
        self.assertNotIn("Build a small Python program for me.", body)
        self.assertTrue(ladder[0].prompt.startswith("Build a small Python program for me."))

    def test_hints_are_stored_with_the_level(self):
        data = zip_of(TRIAGE, add={"levels/01-classify/hints.md": "First.\n---\nSecond."})
        self.upload(data)

        self.assertEqual(load_ladder(self.items)[0].hint_tiers, ["First.", "Second."])

    def test_assignments_follow_their_order(self):
        self.upload()
        other = zip_of(TRIAGE, drop=("assignment.json",), add={"assignment.json": json.dumps({"id": "extract", "name": "Extract", "order": 0 + 2})})
        self.upload(other)

        self.assertEqual([row["id"] for row in assignments(self.items)], ["triage", "extract"])
        self.assertEqual(load_ladder(self.items)[-1].assignment, "extract")

    def test_uploading_again_makes_a_new_version(self):
        self.assertEqual(self.upload(), 1)
        self.assertEqual(self.upload(), 2)

    def test_the_hidden_tickets_stay_out_of_the_database(self):
        self.upload()

        dump = json.dumps([row for row in self.items.rows.values()], default=str)
        self.assertNotIn("T-900", dump)
        self.assertNotIn('"expected"', dump)

    def test_assets_load_five_tickets_and_a_checker(self):
        self.upload()

        assets = load_assets(self.items, self.blobs, "triage", "Reply")

        self.assertEqual(len(assets.tickets), 5)
        ticket = assets.tickets[1]
        good = dict(ticket["expected"], id=ticket["input"]["id"], reply=f"Hi, we are on {ticket['input']['id']}.")
        self.assertEqual(assets.checker(ticket, good), [])

    def test_the_reply_checker_enforces_its_rules(self):
        self.upload()
        assets = load_assets(self.items, self.blobs, "triage", "Reply")
        ticket = assets.tickets[3]
        base = dict(ticket["expected"], id=ticket["input"]["id"])

        no_id = assets.checker(ticket, dict(base, reply="Thanks for writing."))
        long = assets.checker(ticket, dict(base, reply=ticket["input"]["id"] + " word" * 80))
        refund = assets.checker(ticket, dict(base, reply=ticket["input"]["id"] + " we will refund you"))

        self.assertIn("reply does not contain the ticket id", no_id)
        self.assertIn("reply is 80 words or more", long)
        self.assertIn("reply says refund but the ticket does not", refund)

    def test_a_bundle_without_instructions_says_what_is_missing(self):
        data = zip_of(TRIAGE, drop=("levels/02-route/instructions.md",))

        with self.assertRaises(BundleError) as caught:
            parse_bundle(data)

        self.assertIn("levels/02-route/instructions.md is missing or empty", caught.exception.problems)

    def test_a_bundle_with_four_tickets_is_refused(self):
        tickets = fake_tickets("01-classify")[:4]
        data = zip_of(TRIAGE, drop=("levels/01-classify/tickets.json",), add={"levels/01-classify/tickets.json": json.dumps(tickets)})

        with self.assertRaises(BundleError) as caught:
            parse_bundle(data)

        self.assertTrue(any("needs exactly 5 tickets" in p for p in caught.exception.problems))

    def test_a_checker_that_accepts_nothing_is_refused(self):
        data = zip_of(TRIAGE, add={"levels/01-classify/checker.py": "def check(ticket, output):\n    return ['no']\n"})

        with self.assertRaises(BundleError) as caught:
            parse_bundle(data)

        self.assertTrue(any("rejects the expected answer" in p for p in caught.exception.problems))

    def test_a_checker_that_accepts_anything_is_refused(self):
        data = zip_of(TRIAGE, add={"levels/01-classify/checker.py": "def check(ticket, output):\n    return []\n"})

        with self.assertRaises(BundleError) as caught:
            parse_bundle(data)

        self.assertTrue(any("accepts an empty answer" in p for p in caught.exception.problems))

    def test_something_that_is_not_a_zip_is_refused(self):
        with self.assertRaises(BundleError):
            parse_bundle(b"not a zip")

    def test_a_bundle_inside_one_folder_is_accepted(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in TRIAGE.rglob("*"):
                if path.is_file() and path.name != "tickets.json":
                    archive.writestr("triage/" + path.relative_to(TRIAGE).as_posix(), path.read_bytes())
            for level in sorted((TRIAGE / "levels").iterdir()):
                archive.writestr(f"triage/levels/{level.name}/tickets.json", json.dumps(fake_tickets(level.name)))

        self.assertEqual(parse_bundle(buffer.getvalue()).id, "triage")


if __name__ == "__main__":
    unittest.main()
