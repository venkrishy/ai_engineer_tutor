import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fakes import MemoryItems

from tutor.clerk import StudentCard
from tutor.store import Conflict, Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.items = MemoryItems()
        self.store = Store(self.items)

    def test_an_unknown_email_has_no_card(self):
        self.assertIsNone(self.store.load_card("a@example.com"))

    def test_a_saved_card_loads_back_the_same(self):
        card = StudentCard(
            email="a@example.com",
            open_level="Route",
            graded_tries_today=3,
            graded_day=date(2026, 11, 2),
            last_result="fail",
            fails_on_level=2,
        )
        self.store.save_card(card)

        loaded = Store(self.items).load_card("a@example.com")

        self.assertEqual(loaded.open_level, "Route")
        self.assertEqual(loaded.graded_tries_today, 3)
        self.assertEqual(loaded.graded_day, date(2026, 11, 2))
        self.assertEqual(loaded.last_result, "fail")
        self.assertEqual(loaded.fails_on_level, 2)
        self.assertEqual(loaded.assignment_id, "triage")
        self.assertIsNotNone(loaded.registered_at)

    def test_the_item_holds_the_level_index_for_the_dashboard(self):
        self.store.save_card(StudentCard(email="a@example.com", open_level="Reply"))

        self.assertEqual(self.items.get("STUDENT#a@example.com", "CARD")["level_index"], 2)

    def test_two_writers_with_the_same_loaded_version_conflict(self):
        self.store.save_card(StudentCard(email="a@example.com", open_level="Classify"))
        first, second = Store(self.items), Store(self.items)
        card_one = first.load_card("a@example.com")
        card_two = second.load_card("a@example.com")

        first.save_card(card_one)

        with self.assertRaises(Conflict):
            second.save_card(card_two)

    def test_a_new_card_cannot_overwrite_one_made_meanwhile(self):
        other = Store(self.items)
        self.assertIsNone(self.store.load_card("a@example.com"))
        other.save_card(StudentCard(email="a@example.com"))

        with self.assertRaises(Conflict):
            self.store.save_card(StudentCard(email="a@example.com"))

    def test_a_message_id_can_be_claimed_once(self):
        self.assertTrue(self.store.claim("m1", "a@example.com"))
        self.assertFalse(self.store.claim("m1", "b@example.com"))

    def test_a_released_message_id_can_be_claimed_again(self):
        self.store.claim("m1", "a@example.com")
        self.store.release("m1")

        self.assertTrue(self.store.claim("m1", "a@example.com"))

    def test_events_come_back_in_time_order_for_one_student(self):
        self.store.record_event("a@example.com", "m1", "letter", "hello")
        self.store.record_event("b@example.com", "m2", "letter", "other")

        events = self.store.events("a@example.com")

        self.assertEqual([e["message_id"] for e in events], ["m1"])

    def test_cards_lists_every_student(self):
        self.store.save_card(StudentCard(email="a@example.com"))
        self.store.save_card(StudentCard(email="b@example.com"))
        self.store.record_event("a@example.com", "m1", "letter")

        self.assertEqual(
            sorted(row["email"] for row in self.store.cards()),
            ["a@example.com", "b@example.com"],
        )

    def test_global_tries_count_up_per_day(self):
        day = date(2026, 11, 2)
        self.assertEqual(self.store.global_tries(day), 0)

        self.store.add_global_tries(day)
        self.store.add_global_tries(day, 2)

        self.assertEqual(self.store.global_tries(day), 3)
        self.assertEqual(self.store.global_tries(date(2026, 11, 3)), 0)

    def test_settings_keep_what_the_admin_sets(self):
        self.store.set_setting("paused", True)
        self.store.set_setting("note", "x")

        self.assertEqual(self.store.settings()["paused"], True)
        self.assertEqual(self.store.settings()["note"], "x")


if __name__ == "__main__":
    unittest.main()
