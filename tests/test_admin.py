import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fakes import MemoryBlobs, MemoryItems
from test_catalog import TRIAGE, zip_of

from tutor.admin import AdminApp, Request, from_function_url, to_function_url
from tutor.clerk import StudentCard
from tutor.store import Store

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


class FakeLetters:
    def __init__(self, letters):
        self.letters = letters

    def recent(self, limit):
        return [{"key": key, "at": "2026-11-02T10:00:00+00:00", "size": len(raw)} for key, raw in self.letters.items()][:limit]

    def read(self, key):
        return self.letters[key]


LETTER = (
    b"From: Ann <ann@example.com>\r\nTo: tutor@theaiguru.dev\r\nSubject: Hello\r\n"
    b"X-SES-Spam-Verdict: PASS\r\nX-SES-Virus-Verdict: PASS\r\n\r\nI am ready.\r\n"
)


class AdminTest(unittest.TestCase):
    def setUp(self):
        self.items = MemoryItems()
        self.blobs = MemoryBlobs()
        self.store = Store(self.items)
        self.app = AdminApp(self.store, self.items, self.blobs, FakeLetters({"raw/abc": LETTER}), "s3cret", now=lambda: NOW)

    def signed_in(self):
        return "session=" + self.app.make_cookie()

    def call(self, method, path, body=b"", cookie=None):
        return self.app.handle(Request(method, path, self.signed_in() if cookie is None else cookie, body))

    def test_the_page_is_served_without_signing_in(self):
        response = self.app.handle(Request("GET", "/"))

        self.assertEqual(response.status, 200)
        self.assertIn("Mail tutor admin", response.body)

    def test_the_api_refuses_a_visitor_who_has_not_signed_in(self):
        for path in ("/api/students", "/api/letters", "/api/assignments", "/api/settings"):
            self.assertEqual(self.call("GET", path, cookie="").status, 401, path)

    def test_a_wrong_password_is_refused_and_a_right_one_sets_a_cookie(self):
        wrong = self.app.handle(Request("POST", "/api/login", body=b'{"password": "nope"}'))
        right = self.app.handle(Request("POST", "/api/login", body=b'{"password": "s3cret"}'))

        self.assertEqual(wrong.status, 401)
        self.assertIsNone(wrong.cookie)
        self.assertEqual(right.status, 200)
        self.assertEqual(self.call("GET", "/api/settings", cookie="session=" + right.cookie).status, 200)

    def test_a_tampered_or_expired_cookie_is_refused(self):
        expires, signature = self.app.make_cookie().split(".")
        later = AdminApp(self.store, self.items, self.blobs, FakeLetters({}), "s3cret", now=lambda: datetime(2026, 11, 3, tzinfo=timezone.utc))

        self.assertEqual(self.call("GET", "/api/settings", cookie=f"session={int(expires) + 99999}.{signature}").status, 401)
        self.assertEqual(later.handle(Request("GET", "/api/settings", self.signed_in())).status, 401)

    def test_students_are_listed_with_their_level(self):
        self.store.save_card(StudentCard(email="a@example.com", open_level="Route"))

        rows = json.loads(self.call("GET", "/api/students").body)

        self.assertEqual(rows[0]["email"], "a@example.com")
        self.assertEqual((rows[0]["open_level"], rows[0]["level_index"]), ("Route", 1))

    def test_a_student_shows_history(self):
        self.store.save_card(StudentCard(email="a@example.com"))
        self.store.record_event("a@example.com", "m1", "letter", "Hello")

        data = json.loads(self.call("GET", "/api/students/a@example.com").body)

        self.assertEqual(data["card"]["email"], "a@example.com")
        self.assertEqual(data["events"][0]["kind"], "letter")

    def test_resetting_a_student_removes_the_card_and_history(self):
        self.store.save_card(StudentCard(email="a@example.com"))
        self.store.record_event("a@example.com", "m1", "letter")

        self.call("DELETE", "/api/students/a@example.com")

        self.assertIsNone(Store(self.items).load_card("a@example.com"))
        self.assertEqual(self.call("GET", "/api/students/a@example.com").status, 404)

    def test_letters_show_sender_subject_and_verdicts(self):
        rows = json.loads(self.call("GET", "/api/letters").body)

        self.assertEqual(rows[0]["subject"], "Hello")
        self.assertEqual(rows[0]["spam"], "PASS")

    def test_one_letter_shows_its_body(self):
        data = json.loads(self.call("GET", "/api/letter/raw/abc").body)

        self.assertEqual(data["body"].strip(), "I am ready.")

    def test_only_saved_letters_can_be_read(self):
        self.assertEqual(self.call("GET", "/api/letter/secrets/x").status, 404)

    def test_an_assignment_can_be_uploaded_and_listed(self):
        uploaded = self.call("POST", "/api/assignments", zip_of(TRIAGE))
        listed = json.loads(self.call("GET", "/api/assignments").body)

        self.assertEqual(json.loads(uploaded.body)["version"], 1)
        self.assertEqual([level["name"] for level in listed[0]["levels"]], ["Classify", "Route", "Reply"])

    def test_a_bad_upload_says_what_is_wrong(self):
        response = self.call("POST", "/api/assignments", zip_of(TRIAGE, drop=("levels/02-route/instructions.md",)))

        self.assertEqual(response.status, 400)
        self.assertIn("levels/02-route/instructions.md is missing or empty", json.loads(response.body)["problems"])

    def test_pausing_registration_is_saved(self):
        self.call("POST", "/api/settings", b'{"paused": true}')

        self.assertTrue(json.loads(self.call("GET", "/api/settings").body)["paused"])
        self.assertTrue(self.store.settings()["paused"])

    def test_function_url_events_round_trip(self):
        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/login",
            "cookies": ["a=b"],
            "body": "e30=",
            "isBase64Encoded": True,
        }

        request = from_function_url(event)
        out = to_function_url(self.app.handle(Request("POST", "/api/login", body=b'{"password":"s3cret"}')))

        self.assertEqual((request.method, request.path, request.body, request.cookie), ("POST", "/api/login", b"{}", "a=b"))
        self.assertIn("HttpOnly", out["cookies"][0])
        self.assertIn("Secure", out["cookies"][0])


if __name__ == "__main__":
    unittest.main()
