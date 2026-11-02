import unittest

from tutor.clerk import Letter, Zip, receive
from tutor.grading import DoorOrder, RoomResult, Submission


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


if __name__ == "__main__":
    unittest.main()
