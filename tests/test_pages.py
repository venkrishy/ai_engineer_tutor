import json
import tempfile
import unittest
from pathlib import Path

from tutor.catalog import compile_checker
from tutor.links import level_folder
from tutor.pages import assignment_page, hints_page, load_level_pages, write_pages

TRIAGE = Path(__file__).resolve().parent.parent / "assignments" / "triage"


class PagesTest(unittest.TestCase):
    def setUp(self):
        self.pages = load_level_pages(TRIAGE)

    def test_the_level_folders_are_named_as_the_email_links_expect(self):
        for page in self.pages:
            self.assertTrue((TRIAGE / "levels" / level_folder(page.position, page.name)).is_dir(), page.name)

    def test_every_sample_output_passes_the_checker_of_its_level(self):
        for page in self.pages:
            folder = TRIAGE / "levels" / page.folder
            source = (folder / "checker.py").read_text() if (folder / "checker.py").exists() else None
            check = compile_checker(source)
            for sample in page.samples:
                expected = {key: value for key, value in sample["output"].items() if key != "reply"}
                ticket = {"input": sample["input"], "expected": expected}
                self.assertEqual(check(ticket, sample["output"]), [], f"{page.name} {sample['input']['id']}")

    def test_a_sample_input_can_be_pasted_inside_single_quotes(self):
        for page in self.pages:
            for sample in page.samples:
                self.assertNotIn("'", json.dumps(sample["input"]))

    def test_samples_are_not_the_hidden_tickets_when_those_are_present(self):
        for page in self.pages:
            hidden = TRIAGE / "levels" / page.folder / "tickets.json"
            if not hidden.exists():
                continue
            secret = json.loads(hidden.read_text())
            ids = {ticket["input"]["id"] for ticket in secret}
            subjects = {ticket["input"]["subject"].lower() for ticket in secret}
            for sample in page.samples:
                self.assertNotIn(sample["input"]["id"], ids)
                self.assertNotIn(sample["input"]["subject"].lower(), subjects)

    def test_the_committed_pages_are_up_to_date(self):
        with tempfile.TemporaryDirectory() as scratch:
            copy = Path(scratch) / "triage"
            for path in TRIAGE.rglob("*"):
                if path.is_file() and path.name != "tickets.json":
                    target = copy / path.relative_to(TRIAGE)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            for written in write_pages(copy):
                committed = TRIAGE / written.relative_to(copy)
                self.assertEqual(written.read_text(), committed.read_text(), f"run scripts/build_pages.py: {committed}")

    def test_the_assignment_page_shows_samples_and_the_zip_tree_but_not_the_prompt(self):
        page = self.pages[0]
        text = assignment_page(page)

        self.assertIn("Refund for a cancelled order", text)
        self.assertIn("classify.zip", text)
        self.assertIn("└── main.py", text)
        self.assertIn("python3 main.py", text)
        self.assertNotIn(page.prompt[:60], text)

    def test_the_hints_page_has_the_tiered_hints_and_the_copyable_prompt(self):
        page = self.pages[0]
        text = hints_page(page)

        self.assertEqual(text.count("<details>"), 2)
        self.assertIn('id="prompt"', text)
        self.assertIn("Build a small Python program for me.", text)
        self.assertIn("With GitHub Copilot", text)

    def test_text_in_a_page_is_escaped(self):
        page = self.pages[0].__class__(**{**self.pages[0].__dict__, "title": "<script>x</script>"})

        self.assertNotIn("<script>x", assignment_page(page))
