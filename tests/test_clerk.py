import unittest
from datetime import date

from tutor.clerk import Letter, StudentCard, Zip, receive
from tutor.grading import RoomResult


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
    def grade(self, submission) -> RoomResult:
        raise AssertionError("the room stayed shut")


class RecordingDoor:
    def __init__(self, statuses=None):
        self.statuses = list(statuses or ["available"])
        self.created = []
        self.deleted = []
        self.phase = "closed"

    def start_create(self, order):
        self.phase = "opening"
        endpoint_id = f"vpce-{len(self.created) + 1}"
        self.created.append(endpoint_id)
        return endpoint_id

    def status(self, endpoint_id):
        status = self.statuses.pop(0) if self.statuses else "available"
        if status == "available":
            self.phase = "open"
        return status

    def delete(self, endpoint_id):
        self.deleted.append(endpoint_id)
        self.phase = "closed"


class QueuedRoom:
    def __init__(self, results):
        self.results = list(results)
        self.graded = []

    def grade(self, submission):
        self.graded.append(submission.message_id)
        return self.results.pop(0)


class ScriptedRoom:
    def __init__(self, result):
        self.result = result
        self.graded = []

    def grade(self, submission):
        self.graded.append(submission.message_id)
        return self.result


class PassingRoom:
    def __init__(self, cards):
        self.cards = cards
        self.graded = []
        self.in_flight = None

    def grade(self, submission):
        self.graded.append(submission.message_id)
        self.in_flight = self.cards[submission.email].in_flight
        return RoomResult.PASS


class RoomGrade:
    def __init__(self, result, findings=""):
        self.result = result
        self.findings = findings


class FixedNote:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def note(self, assignment, result):
        self.calls.append((assignment, result))
        return self.text


TODAY = date(2026, 11, 2)
NOTE = "The labels match the ticket."
ROUTE_BODY = "\n".join(
    [
        "Route",
        "",
        "Read one ticket as JSON and print one JSON object with the ticket id, a label (bug, billing, access, or other), a priority (P1, P2, P3), and a queue.",
        "",
        "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
        "",
        "Bugs go to engineering, billing goes to billing, and the rest go to support. P1 means work is blocked or money is wrong. P3 is a how-to. P2 is the rest.",
        "",
        "Sample ticket:",
        '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
    ]
)
REPLY_BODY = "\n".join(
    [
        "Reply",
        "",
        "Read one ticket as JSON and print one JSON object with the ticket id, a label (bug, billing, access, or other), a priority (P1, P2, P3), a queue, and a short customer reply.",
        "",
        "Billing means charges, invoices, refunds, or payment. Access means login, password, or permissions. Bug means the product is broken. Everything else is other.",
        "",
        "Bugs go to engineering, billing goes to billing, and the rest go to support. P1 means work is blocked or money is wrong. P3 is a how-to. P2 is the rest.",
        "",
        'The customer reply must contain the ticket id, stay under 80 words, and say "refund" only when the ticket does.',
        "",
        "Sample ticket:",
        '{"id": "T-100", "subject": "I was charged twice", "body": "My invoice shows two payments for the same month."}',
    ]
)


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

    def test_a_zip_with_main_py_inside_a_single_folder_is_graded(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        room = PassingRoom(cards)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("work/main.py", "work/helper.py"), 128))],
            cards,
            door=RecordingDoor(),
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(replies[0].body.splitlines()[0], "Pass")
        self.assertEqual(room.graded, ["m2"])
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Route")
        self.assertEqual(card.graded_tries_today, 1)
        self.assertFalse(card.in_flight)

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

    def test_an_accepted_zip_is_graded_pass_and_the_next_assignment_rides_along(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        door = RecordingDoor()
        room = PassingRoom(cards)
        model = FixedNote(NOTE)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py", "util.py"), 10 * 1024 * 1024))],
            cards,
            door=door,
            room=room,
            model=model,
            today=TODAY,
        )

        self.assertEqual(
            [(reply.email, reply.message_id, reply.body) for reply in replies],
            [("a@example.com", "m2", "\n\n".join(["Pass", NOTE, ROUTE_BODY]))],
        )
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Route")
        self.assertEqual(card.last_result, "pass")
        self.assertEqual(card.graded_tries_today, 1)
        self.assertEqual(card.graded_day, TODAY)
        self.assertFalse(card.finished)
        self.assertFalse(card.in_flight)
        self.assertEqual(card.handled_message_ids, {"m2"})
        self.assertEqual(room.graded, ["m2"])
        self.assertIs(room.in_flight, True)
        self.assertEqual(model.calls, [("Classify", "pass")])
        self.assertEqual(door.created, ["vpce-1"])
        self.assertEqual(door.deleted, ["vpce-1"])

    def test_a_fail_keeps_the_assignment_and_carries_the_note_and_findings(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=2,
                graded_day=TODAY,
            )
        }
        findings = "expected label bug, got other"
        room = ScriptedRoom(RoomGrade(RoomResult.FAIL, findings))
        model = FixedNote(NOTE)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 100))],
            cards,
            door=RecordingDoor(),
            room=room,
            model=model,
            today=TODAY,
        )

        self.assertEqual(replies[0].body, "\n\n".join(["Fail", NOTE, findings]))
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertEqual(card.last_result, "fail")
        self.assertEqual(card.graded_tries_today, 3)
        self.assertEqual(card.graded_day, TODAY)
        self.assertFalse(card.finished)
        self.assertFalse(card.in_flight)
        self.assertEqual(room.graded, ["m2"])
        self.assertEqual(model.calls, [("Classify", "fail")])

    def test_a_fail_truncates_findings_to_8_kb(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        findings = "FINDINGS-START" + ("x" * 9000) + "FINDINGS-END"
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 100))],
            cards,
            door=RecordingDoor(),
            room=ScriptedRoom(RoomGrade(RoomResult.FAIL, findings)),
            model=FixedNote("NOTE-START keep this note NOTE-END"),
            today=TODAY,
        )

        _fail_line, note, carried = replies[0].body.split("\n\n", 2)
        self.assertEqual(note, "NOTE-START keep this note NOTE-END")
        self.assertEqual(len(carried.encode("utf-8")), 8 * 1024)
        self.assertTrue(carried.startswith("FINDINGS-START"))
        self.assertNotIn("FINDINGS-END", carried)
        self.assertEqual(cards["a@example.com"].open_assignment, "Classify")

    def test_not_graded_leaves_the_assignment_open_and_spends_no_try(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=4,
                graded_day=TODAY,
            )
        }
        model = FixedNote(NOTE)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 100))],
            cards,
            door=RecordingDoor(),
            room=ScriptedRoom(RoomGrade(RoomResult.NOT_GRADED, "checker crashed")),
            model=model,
            today=TODAY,
        )

        self.assertEqual(replies[0].body, "Not graded")
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Classify")
        self.assertEqual(card.last_result, "not graded")
        self.assertEqual(card.graded_tries_today, 4)
        self.assertEqual(card.graded_day, TODAY)
        self.assertFalse(card.finished)
        self.assertFalse(card.in_flight)
        self.assertEqual(model.calls, [])
        self.assertEqual(card.handled_message_ids, {"m2"})

    def test_a_pass_on_route_opens_reply(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Route",
                graded_tries_today=1,
                graded_day=TODAY,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m3", Zip(("main.py",), 100))],
            cards,
            door=RecordingDoor(),
            room=PassingRoom(cards),
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(replies[0].body, "\n\n".join(["Pass", NOTE, REPLY_BODY]))
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Reply")
        self.assertFalse(card.finished)
        self.assertEqual(card.last_result, "pass")
        self.assertEqual(card.graded_tries_today, 2)

    def test_a_pass_on_reply_finishes_the_ladder(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Reply",
                graded_tries_today=2,
                graded_day=TODAY,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m4", Zip(("main.py",), 100))],
            cards,
            door=RecordingDoor(),
            room=PassingRoom(cards),
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(
            replies[0].body,
            "\n\n".join(["Pass", NOTE, "The ladder is finished."]),
        )
        card = cards["a@example.com"]
        self.assertTrue(card.finished)
        self.assertEqual(card.open_assignment, "Reply")
        self.assertEqual(card.last_result, "pass")
        self.assertEqual(card.graded_tries_today, 3)
        self.assertFalse(card.in_flight)

    def test_a_second_waiting_zip_is_not_graded_and_asks_to_send_it_again(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        room = PassingRoom(cards)
        replies = receive(
            [
                Letter("a@example.com", "m2", Zip(("main.py",), 100)),
                Letter("a@example.com", "m3", Zip(("main.py",), 80)),
            ],
            cards,
            door=RecordingDoor(),
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(
            [(reply.message_id, reply.body.splitlines()[0]) for reply in replies],
            [("m2", "Pass"), ("m3", "Send that zip again after the result.")],
        )
        self.assertEqual(replies[1].body, "Send that zip again after the result.")
        self.assertEqual(room.graded, ["m2"])
        card = cards["a@example.com"]
        self.assertEqual(card.graded_tries_today, 1)
        self.assertEqual(card.last_result, "pass")
        self.assertEqual(card.handled_message_ids, {"m2", "m3"})
        self.assertEqual(card.open_assignment, "Route")

    def test_a_batch_of_accepted_zips_at_the_daily_cap_is_cap_hit_and_the_door_stays_shut(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=10,
            ),
            "b@example.com": StudentCard(
                email="b@example.com",
                open_assignment="Route",
                graded_tries_today=10,
            ),
        }
        room = PassingRoom(cards)
        model = FixedNote(NOTE)
        replies = receive(
            [
                Letter("a@example.com", "m2", Zip(("main.py",), 100)),
                Letter("b@example.com", "m3", Zip(("work/main.py",), 100)),
            ],
            cards,
            door=DoorThatMustStayShut(),
            room=room,
            model=model,
            today=TODAY,
        )

        self.assertEqual(
            [(reply.email, reply.message_id, reply.body) for reply in replies],
            [
                ("a@example.com", "m2", "Cap hit"),
                ("b@example.com", "m3", "Cap hit"),
            ],
        )
        self.assertEqual(room.graded, [])
        self.assertEqual(model.calls, [])
        for email, assignment in (("a@example.com", "Classify"), ("b@example.com", "Route")):
            card = cards[email]
            self.assertEqual(card.last_result, "cap hit")
            self.assertEqual(card.graded_tries_today, 10)
            self.assertEqual(card.open_assignment, assignment)
            self.assertFalse(card.in_flight)
            self.assertFalse(card.finished)

    def test_a_letter_that_arrives_while_the_door_is_opening_joins_this_batch(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            ),
            "b@example.com": StudentCard(
                email="b@example.com",
                open_assignment="Classify",
            ),
        }
        door = RecordingDoor(["pending", "available"])
        sent = {"joined": False}

        def arrive():
            if door.phase == "opening" and not sent["joined"]:
                sent["joined"] = True
                return [Letter("b@example.com", "late", Zip(("main.py",), 40))]
            return []

        room = QueuedRoom([RoomResult.PASS, RoomResult.FAIL])
        replies = receive(
            [Letter("a@example.com", "early", Zip(("main.py",), 40))],
            cards,
            door=door,
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
            arrive=arrive,
        )

        self.assertEqual(room.graded, ["early", "late"])
        self.assertEqual(
            [(reply.message_id, reply.body.splitlines()[0]) for reply in replies],
            [("early", "Pass"), ("late", "Fail")],
        )
        self.assertEqual(cards["a@example.com"].open_assignment, "Route")
        self.assertEqual(cards["a@example.com"].last_result, "pass")
        self.assertEqual(cards["b@example.com"].open_assignment, "Classify")
        self.assertEqual(cards["b@example.com"].last_result, "fail")
        self.assertEqual(cards["b@example.com"].graded_tries_today, 1)
        self.assertEqual(cards["b@example.com"].handled_message_ids, {"late"})
        self.assertEqual(door.created, ["vpce-1"])
        self.assertEqual(door.deleted, ["vpce-1"])

    def test_a_letter_that_arrives_after_grading_has_started_waits(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            ),
            "b@example.com": StudentCard(
                email="b@example.com",
                open_assignment="Classify",
            ),
        }
        door = RecordingDoor()
        sent = {"waited": False}

        def arrive():
            if door.phase == "open" and not sent["waited"]:
                sent["waited"] = True
                return [Letter("b@example.com", "later", Zip(("main.py",), 40))]
            return []

        replies = receive(
            [Letter("a@example.com", "early", Zip(("main.py",), 40))],
            cards,
            door=door,
            room=QueuedRoom([RoomResult.PASS]),
            model=FixedNote(NOTE),
            today=TODAY,
            arrive=arrive,
        )

        self.assertTrue(sent["waited"])
        self.assertEqual([reply.message_id for reply in replies], ["early"])
        self.assertNotIn("later", cards["b@example.com"].handled_message_ids)
        self.assertEqual(cards["b@example.com"].graded_tries_today, 0)
        self.assertIsNone(cards["b@example.com"].last_result)
        self.assertEqual(cards["b@example.com"].open_assignment, "Classify")

        later = receive(
            [Letter("b@example.com", "later", Zip(("main.py",), 40))],
            cards,
            door=RecordingDoor(),
            room=QueuedRoom([RoomResult.FAIL]),
            model=FixedNote(NOTE),
            today=TODAY,
        )
        self.assertEqual(later[0].body.splitlines()[0], "Fail")
        self.assertEqual(cards["b@example.com"].handled_message_ids, {"later"})
        self.assertEqual(cards["b@example.com"].last_result, "fail")
        self.assertEqual(cards["b@example.com"].graded_tries_today, 1)
        self.assertEqual(cards["b@example.com"].open_assignment, "Classify")

    def test_a_second_zip_that_arrives_while_the_student_is_in_flight_asks_to_send_it_again(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        door = RecordingDoor()
        sent = {"extra": False}

        def arrive():
            if door.phase == "open" and not sent["extra"]:
                sent["extra"] = True
                return [Letter("a@example.com", "extra", Zip(("main.py",), 20))]
            return []

        room = PassingRoom(cards)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 40))],
            cards,
            door=door,
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
            arrive=arrive,
        )

        self.assertTrue(sent["extra"])
        self.assertIs(room.in_flight, True)
        self.assertEqual(room.graded, ["m2"])
        self.assertEqual(
            [(reply.message_id, reply.body.splitlines()[0]) for reply in replies],
            [("m2", "Pass"), ("extra", "Send that zip again after the result.")],
        )
        self.assertEqual(replies[1].body, "Send that zip again after the result.")
        card = cards["a@example.com"]
        self.assertEqual(card.graded_tries_today, 1)
        self.assertEqual(card.last_result, "pass")
        self.assertEqual(card.handled_message_ids, {"m2", "extra"})
        self.assertEqual(card.open_assignment, "Route")
        self.assertFalse(card.in_flight)

    def test_the_same_message_id_is_graded_once_and_receives_one_reply(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        letter = Letter("a@example.com", "m2", Zip(("main.py",), 10))
        room = PassingRoom(cards)
        first = receive(
            [letter, letter],
            cards,
            door=RecordingDoor(),
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
        )
        second = receive(
            [letter],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].message_id, "m2")
        self.assertEqual(first[0].body.splitlines()[0], "Pass")
        self.assertEqual(second, [])
        self.assertEqual(room.graded, ["m2"])
        self.assertEqual(cards["a@example.com"].graded_tries_today, 1)
        self.assertEqual(cards["a@example.com"].handled_message_ids, {"m2"})

    def test_the_last_result_is_whichever_happened_most_recently(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=9,
                graded_day=TODAY,
            )
        }
        failed = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 10))],
            cards,
            door=RecordingDoor(),
            room=ScriptedRoom(RoomGrade(RoomResult.FAIL, "missing queue")),
            model=FixedNote(NOTE),
            today=TODAY,
        )
        self.assertEqual(failed[0].body.splitlines()[0], "Fail")
        self.assertEqual(cards["a@example.com"].last_result, "fail")
        self.assertEqual(cards["a@example.com"].graded_tries_today, 10)

        capped = receive(
            [Letter("a@example.com", "m3", Zip(("main.py",), 10))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            model=FixedNote(NOTE),
            today=TODAY,
        )
        self.assertEqual(capped[0].body, "Cap hit")
        self.assertEqual(cards["a@example.com"].last_result, "cap hit")
        self.assertEqual(cards["a@example.com"].graded_tries_today, 10)
        self.assertEqual(cards["a@example.com"].open_assignment, "Classify")

    def test_the_daily_cap_resets_on_the_next_utc_day(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
                graded_tries_today=10,
                graded_day=date(2026, 11, 1),
            )
        }
        room = PassingRoom(cards)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 10))],
            cards,
            door=RecordingDoor(),
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(replies[0].body.splitlines()[0], "Pass")
        self.assertEqual(room.graded, ["m2"])
        card = cards["a@example.com"]
        self.assertEqual(card.graded_tries_today, 1)
        self.assertEqual(card.graded_day, TODAY)
        self.assertEqual(card.last_result, "pass")
        self.assertEqual(card.open_assignment, "Route")

    def test_a_dead_zone_is_not_graded_and_spends_no_try(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Route",
                graded_tries_today=4,
                graded_day=TODAY,
            )
        }
        model = FixedNote(NOTE)
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 10))],
            cards,
            door=RecordingDoor(["failed", "failed", "failed"]),
            room=PassingRoom(cards),
            model=model,
            today=TODAY,
        )

        self.assertEqual(replies[0].body, "Not graded")
        card = cards["a@example.com"]
        self.assertEqual(card.open_assignment, "Route")
        self.assertEqual(card.last_result, "not graded")
        self.assertEqual(card.graded_tries_today, 4)
        self.assertEqual(card.graded_day, TODAY)
        self.assertEqual(model.calls, [])
        self.assertFalse(card.in_flight)

    def test_in_flight_is_true_only_for_the_student_being_graded(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            ),
            "b@example.com": StudentCard(
                email="b@example.com",
                open_assignment="Classify",
            ),
        }

        class FlightRoom:
            def __init__(self):
                self.snapshots = []

            def grade(self, submission):
                self.snapshots.append(
                    {email: cards[email].in_flight for email in cards}
                )
                return RoomResult.PASS

        room = FlightRoom()
        receive(
            [
                Letter("a@example.com", "m2", Zip(("main.py",), 10)),
                Letter("b@example.com", "m3", Zip(("main.py",), 10)),
            ],
            cards,
            door=RecordingDoor(),
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(
            room.snapshots,
            [
                {"a@example.com": True, "b@example.com": False},
                {"a@example.com": False, "b@example.com": True},
            ],
        )
        self.assertFalse(cards["a@example.com"].in_flight)
        self.assertFalse(cards["b@example.com"].in_flight)
        self.assertEqual(cards["a@example.com"].graded_tries_today, 1)
        self.assertEqual(cards["b@example.com"].graded_tries_today, 1)

    def test_a_finished_student_with_an_accepted_zip_is_not_graded(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Reply",
                finished=True,
                graded_tries_today=3,
                graded_day=TODAY,
            )
        }
        replies = receive(
            [Letter("a@example.com", "m9", Zip(("main.py",), 10))],
            cards,
            door=DoorThatMustStayShut(),
            room=RoomThatMustStayShut(),
            today=TODAY,
        )

        self.assertEqual(replies[0].body, "The ladder is finished.")
        card = cards["a@example.com"]
        self.assertTrue(card.finished)
        self.assertEqual(card.graded_tries_today, 3)
        self.assertEqual(card.open_assignment, "Reply")
        self.assertFalse(card.in_flight)

    def test_a_capped_student_does_not_start_a_room_while_another_student_is_graded(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            ),
            "b@example.com": StudentCard(
                email="b@example.com",
                open_assignment="Classify",
                graded_tries_today=10,
            ),
        }
        room = QueuedRoom([RoomResult.PASS])
        replies = receive(
            [
                Letter("a@example.com", "free", Zip(("main.py",), 10)),
                Letter("b@example.com", "capped", Zip(("main.py",), 10)),
            ],
            cards,
            door=RecordingDoor(),
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
        )

        self.assertEqual(room.graded, ["free"])
        self.assertEqual(replies[0].body.splitlines()[0], "Pass")
        self.assertEqual(replies[1].body, "Cap hit")
        self.assertEqual(cards["a@example.com"].graded_tries_today, 1)
        self.assertEqual(cards["a@example.com"].last_result, "pass")
        self.assertEqual(cards["b@example.com"].graded_tries_today, 10)
        self.assertEqual(cards["b@example.com"].last_result, "cap hit")
        self.assertEqual(cards["b@example.com"].open_assignment, "Classify")
        self.assertFalse(cards["b@example.com"].in_flight)

    def test_a_second_zip_that_arrives_while_the_door_is_opening_is_not_another_submission(self):
        cards = {
            "a@example.com": StudentCard(
                email="a@example.com",
                open_assignment="Classify",
            )
        }
        door = RecordingDoor(["pending", "available"])
        sent = {"extra": False}

        def arrive():
            if door.phase == "opening" and not sent["extra"]:
                sent["extra"] = True
                return [Letter("a@example.com", "extra", Zip(("main.py",), 20))]
            return []

        room = QueuedRoom([RoomResult.PASS])
        replies = receive(
            [Letter("a@example.com", "m2", Zip(("main.py",), 40))],
            cards,
            door=door,
            room=room,
            model=FixedNote(NOTE),
            today=TODAY,
            arrive=arrive,
        )

        self.assertTrue(sent["extra"])
        self.assertEqual(room.graded, ["m2"])
        self.assertEqual(
            [(reply.message_id, reply.body.splitlines()[0]) for reply in replies],
            [("m2", "Pass"), ("extra", "Send that zip again after the result.")],
        )
        self.assertEqual(cards["a@example.com"].graded_tries_today, 1)
        self.assertEqual(cards["a@example.com"].handled_message_ids, {"m2", "extra"})

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
