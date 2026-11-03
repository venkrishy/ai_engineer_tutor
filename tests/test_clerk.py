import unittest

from tutor.clerk import Letter, StudentCard, Zip, receive
from tutor.grading import DoorOrder, RoomResult, Submission


CLASSIFY_BODY = "\n".join(
    [
        "Classify",
        "",
        "Read one ticket as JSON and print one JSON object with the ticket id and a label: bug, billing, access, or other.",
        "",
        "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
        "",
        "Sample ticket:",
        '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
    ]
)


class DoorThatMustStayShut:
    def start_create(self, order: DoorOrder) -> str:
        raise AssertionError("the door stayed shut")

    def status(self, endpoint_id: str) -> str:
        raise AssertionError("the door stayed shut")

    def delete(self, endpoint_id: str) -> None:
        raise AssertionError("the door stayed shut")


class RoomThatMustStayShut:
    def grade(self, submission: Submission) -> RoomResult:
        raise AssertionError("the room stayed shut")


class ClerkTest(unittest.TestCase):
    def test_a_first_letter_creates_the_student_and_replies_with_the_first_assignment(self):
        cards: dict = {}
        replies = receive(
            [Letter("a@example.com", "m1")],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(
            [(reply.email, reply.message_id, reply.body) for reply in replies],
            [
                (
                    "a@example.com",
                    "m1",
                    "\n".join(
                        [
                            "Classify",
                            "",
                            "Read one ticket as JSON and print one JSON object with the ticket id and a label: bug, billing, access, or other.",
                            "",
                            "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
                            "",
                            "Sample ticket:",
                            '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
                        ]
                    ),
                )
            ],
        )
        card = cards["a@example.com"]
        self.assertEqual(card.email, "a@example.com")
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(list(cards), ["a@example.com"])

    def test_a_zip_on_the_first_letter_is_ignored(self):
        cards: dict = {}
        replies = receive(
            [Letter("a@example.com", "m1", Zip(("main.py",), 100))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body.splitlines()[0], "Classify")
        self.assertFalse(cards["a@example.com"].in_flight)
        self.assertEqual(cards["a@example.com"].open_assignment, "Classify")

    def test_the_same_message_id_creates_one_student_and_one_reply(self):
        cards: dict = {}
        letter = Letter("a@example.com", "m1")
        first = receive(
            [letter],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )
        second = receive(
            [letter, letter],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(list(cards), ["a@example.com"])
        self.assertEqual(cards["a@example.com"].open_assignment, "Classify")

    def test_the_same_message_id_from_another_address_does_not_create_a_second_student(self):
        cards: dict = {}
        receive(
            [Letter("a@example.com", "m1")],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )
        second = receive(
            [Letter("b@example.com", "m1")],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(second, [])
        self.assertEqual(list(cards), ["a@example.com"])

    def test_more_than_one_attachment_asks_for_a_single_zip(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", attachment_count=2)],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(
            [(reply.email, reply.message_id, reply.body) for reply in replies],
            [("a@example.com", "m2", "Send a single zip.")],
        )
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)
        self.assertEqual(card.handled_message_ids, {"m2"})

    def test_a_zip_over_10_mb_asks_for_a_single_zip(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=3,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 11 * 1024 * 1024))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "Send a single zip.")
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 3)

    def test_a_zip_without_main_py_asks_for_a_single_zip(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("readme.txt",), 128))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "Send a single zip.")
        card = cards["a@example.com"]
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)
        self.assertEqual(card.open_assignment, "Classify")

    def test_a_zip_with_main_py_inside_a_single_folder_keeps_the_open_assignment(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("work/main.py", "work/helper.py"), 128))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, CLASSIFY_BODY)
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)

    def test_a_zip_with_main_py_deeper_than_one_folder_asks_for_a_single_zip(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("work/src/main.py",), 128))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "Send a single zip.")
        card = cards["a@example.com"]
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)

    def test_a_zip_with_main_py_beside_another_top_level_name_asks_for_a_single_zip(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("work/main.py", "readme.txt"), 128))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "Send a single zip.")
        card = cards["a@example.com"]
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)

    def test_a_letter_with_no_zip_receives_the_open_assignment_again(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=2,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2")],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(
            [(reply.email, reply.message_id, reply.body) for reply in replies],
            [("a@example.com", "m2", CLASSIFY_BODY)],
        )
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 2)

    def test_a_letter_with_no_zip_at_the_daily_cap_receives_the_open_assignment(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=10,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2")],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, CLASSIFY_BODY)
        card = cards["a@example.com"]
        self.assertEqual(card.graded_tries_today, 10)
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)

    def test_a_finished_student_with_no_zip_hears_the_ladder_is_finished(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                finished=True,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2")],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "The ladder is finished.")
        card = cards["a@example.com"]
        self.assertTrue(card.finished)
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)
        self.assertEqual(card.open_assignment, "Classify")

    def test_a_finished_student_with_a_rejected_zip_hears_the_ladder_is_finished(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                finished=True,
                graded_tries_today=4,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("readme.txt",), 128))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "The ladder is finished.")
        card = cards["a@example.com"]
        self.assertTrue(card.finished)
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 4)
        self.assertEqual(card.open_assignment, "Classify")

    def test_a_rejected_zip_on_the_first_letter_is_ignored(self):
        cards: dict = {}
        replies = receive(
            [Letter("a@example.com", "m1", Zip(("notes.txt",), 11 * 1024 * 1024))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, CLASSIFY_BODY)
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)
        self.assertEqual(list(cards), ["a@example.com"])

    def test_main_py_at_the_top_keeps_the_open_assignment(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py", "util.py"), 10 * 1024 * 1024))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, CLASSIFY_BODY)
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertFalse(card.in_flight)
        self.assertEqual(card.graded_tries_today, 0)

    def test_a_rejected_zip_at_the_daily_cap_asks_for_a_single_zip(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=10,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("notes.txt",), 128))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
        )

        self.assertEqual(replies[0].body, "Send a single zip.")
        card = cards["a@example.com"]
        self.assertEqual(card.graded_tries_today, 10)
        self.assertFalse(card.in_flight)
        self.assertEqual(card.open_assignment, "Classify")


if __name__ == "__main__":
    unittest.main()
