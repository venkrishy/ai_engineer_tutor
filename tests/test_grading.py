import json
import unittest
from datetime import date

from tutor.grading import (
    DAILY_GRADED_ATTEMPT_CAP,
    FOUNDATION_MODEL_ID,
    HOME_REGION,
    PROFILE_ID,
    PROFILE_REGIONS,
    DoorOrder,
    Outcome,
    Quota,
    RoomResult,
    Submission,
    door_order,
    ec2_create_vpc_endpoint_args,
    endpoint_policy,
    graded_attempts_on,
    profile_arn,
    result_by_id,
    room_role_policy,
    run_batch,
)

TODAY = date(2026, 11, 2)
ACCOUNT = "123456789012"
VPC = "vpc-1"
SUBNET = "subnet-a"
SECURITY_GROUP = "sg-1"


class FakeDoor:
    def __init__(self, statuses: list[str] | None = None):
        self.statuses = list(statuses or ["available"])
        self.orders: list[DoorOrder] = []
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.live = 0
        self.fail_delete = False

    def start_create(self, order: DoorOrder) -> str:
        if self.live:
            raise RuntimeError("an endpoint is already open")
        self.orders.append(order)
        self.live += 1
        endpoint_id = f"vpce-{len(self.created) + 1}"
        self.created.append(endpoint_id)
        return endpoint_id

    def status(self, endpoint_id: str) -> str:
        if not self.statuses:
            return "available"
        return self.statuses.pop(0)

    def delete(self, endpoint_id: str) -> None:
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.live -= 1
        self.deleted.append(endpoint_id)


class ScriptedRoom:
    def __init__(self, script: list[RoomResult | Exception]):
        self.script = list(script)
        self.graded: list[str] = []

    def grade(self, submission: Submission) -> RoomResult:
        self.graded.append(submission.message_id)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class GradingBatchTest(unittest.TestCase):
    def run_batch(self, waiting, quotas=None, door=None, room=None, **kwargs):
        return run_batch(
            waiting,
            {} if quotas is None else quotas,
            door=door if door is not None else FakeDoor(),
            room=room if room is not None else ScriptedRoom([]),
            today=kwargs.pop("today", TODAY),
            account_id=ACCOUNT,
            vpc_id=VPC,
            subnet_id=SUBNET,
            security_group_id=SECURITY_GROUP,
            pause=kwargs.pop("pause", lambda _seconds: None),
            **kwargs,
        )

    def test_idle_queue_does_not_create_an_endpoint(self):
        door = FakeDoor()
        result = self.run_batch([], door=door)
        self.assertEqual(result.endpoint_creates, 0)
        self.assertEqual(door.created, [])

    def test_capped_student_does_not_open_the_door(self):
        door = FakeDoor()
        room = ScriptedRoom([])
        quotas = {"a@example.com": Quota(TODAY, DAILY_GRADED_ATTEMPT_CAP)}
        result = self.run_batch(
            [Submission("a@example.com", "m1")],
            quotas,
            door=door,
            room=room,
        )
        self.assertEqual(result.endpoint_creates, 0)
        self.assertEqual(room.graded, [])
        self.assertEqual(result_by_id(result)["m1"].outcome, Outcome.CAPPED)
        self.assertFalse(result_by_id(result)["m1"].counts_toward_cap)
        self.assertEqual(quotas["a@example.com"].graded_attempts, DAILY_GRADED_ATTEMPT_CAP)

    def test_one_batch_opens_one_zone_and_closes_the_door(self):
        door = FakeDoor()
        room = ScriptedRoom([RoomResult.PASS, RoomResult.FAIL, RoomResult.PASS])
        pauses: list[float] = []
        waiting = [
            Submission("a@example.com", "m1"),
            Submission("b@example.com", "m2"),
            Submission("c@example.com", "m3"),
        ]
        result = self.run_batch(
            waiting,
            door=door,
            room=room,
            pause=pauses.append,
        )
        self.assertEqual(result.endpoint_creates, 1)
        self.assertEqual(result.endpoint_deletes, 1)
        self.assertEqual(door.live, 0)
        self.assertEqual(pauses, [])
        order = door.orders[0]
        self.assertEqual(order.subnet_ids, (SUBNET,))
        self.assertEqual(order.service_name, "com.amazonaws.us-east-1.bedrock-runtime")
        self.assertTrue(order.private_dns)
        self.assertEqual(len(ec2_create_vpc_endpoint_args(order)["SubnetIds"]), 1)
        self.assertEqual(
            [item.outcome for item in result.items],
            [Outcome.PASS, Outcome.FAIL, Outcome.PASS],
        )
        self.assertTrue(all(item.counts_toward_cap for item in result.items))

    def test_mail_that_arrives_while_the_door_opens_joins_the_batch(self):
        door = FakeDoor(["pending", "available"])
        room = ScriptedRoom([RoomResult.PASS, RoomResult.FAIL])
        extra = {"n": 0}

        def arrive():
            extra["n"] += 1
            if extra["n"] == 1:
                return []
            if extra["n"] == 2:
                return [Submission("late@example.com", "late")]
            return []

        result = self.run_batch(
            [Submission("early@example.com", "early")],
            door=door,
            room=room,
            arrive=arrive,
        )
        self.assertEqual(result.endpoint_creates, 1)
        self.assertEqual(room.graded, ["early", "late"])
        self.assertEqual(result_by_id(result)["late"].outcome, Outcome.FAIL)

    def test_pass_and_fail_spend_a_daily_attempt(self):
        quotas: dict[str, Quota] = {}
        self.run_batch(
            [Submission("a@example.com", "m1"), Submission("a@example.com", "m2")],
            quotas,
            room=ScriptedRoom([RoomResult.PASS, RoomResult.FAIL]),
        )
        self.assertEqual(graded_attempts_on(quotas["a@example.com"], TODAY), 2)

    def test_not_graded_does_not_spend_an_attempt(self):
        quotas = {"a@example.com": Quota(TODAY, DAILY_GRADED_ATTEMPT_CAP - 1)}
        room = ScriptedRoom([RoomResult.NOT_GRADED, RoomResult.PASS])
        result = self.run_batch(
            [Submission("a@example.com", "m1"), Submission("a@example.com", "m2")],
            quotas,
            room=room,
        )
        self.assertEqual(result_by_id(result)["m1"].outcome, Outcome.NOT_GRADED)
        self.assertFalse(result_by_id(result)["m1"].counts_toward_cap)
        self.assertEqual(result_by_id(result)["m2"].outcome, Outcome.PASS)
        self.assertEqual(quotas["a@example.com"].graded_attempts, DAILY_GRADED_ATTEMPT_CAP)

    def test_the_graded_attempt_after_the_cap_does_not_start_a_room(self):
        quotas = {"a@example.com": Quota(TODAY, DAILY_GRADED_ATTEMPT_CAP - 1)}
        room = ScriptedRoom([RoomResult.PASS])
        result = self.run_batch(
            [Submission("a@example.com", "m1"), Submission("a@example.com", "m2")],
            quotas,
            room=room,
        )
        self.assertEqual(room.graded, ["m1"])
        self.assertEqual(result_by_id(result)["m2"].outcome, Outcome.CAPPED)
        self.assertEqual(quotas["a@example.com"].graded_attempts, DAILY_GRADED_ATTEMPT_CAP)

    def test_the_cap_resets_on_the_next_utc_day(self):
        quotas = {"a@example.com": Quota(date(2026, 11, 1), DAILY_GRADED_ATTEMPT_CAP)}
        room = ScriptedRoom([RoomResult.PASS])
        result = self.run_batch(
            [Submission("a@example.com", "m1")],
            quotas,
            room=room,
        )
        self.assertEqual(result_by_id(result)["m1"].outcome, Outcome.PASS)
        self.assertEqual(quotas["a@example.com"].attempt_day, TODAY)
        self.assertEqual(quotas["a@example.com"].graded_attempts, 1)

    def test_a_dead_zone_retries_then_does_not_grade_or_count(self):
        door = FakeDoor(["failed", "failed", "failed"])
        room = ScriptedRoom([])
        quotas = {"a@example.com": Quota(TODAY, 4)}
        pauses: list[float] = []
        result = self.run_batch(
            [Submission("a@example.com", "m1")],
            quotas,
            door=door,
            room=room,
            pause=pauses.append,
        )
        self.assertEqual(result.endpoint_creates, 3)
        self.assertEqual(result.endpoint_deletes, 3)
        self.assertEqual(door.live, 0)
        self.assertEqual(pauses, [60, 120])
        self.assertEqual(room.graded, [])
        self.assertEqual(result_by_id(result)["m1"].outcome, Outcome.NOT_GRADED)
        self.assertFalse(result_by_id(result)["m1"].counts_toward_cap)
        self.assertEqual(quotas["a@example.com"].graded_attempts, 4)

    def test_a_zone_that_recovers_grades_on_the_next_try(self):
        door = FakeDoor(["failed", "available"])
        room = ScriptedRoom([RoomResult.PASS])
        pauses: list[float] = []
        result = self.run_batch(
            [Submission("a@example.com", "m1")],
            door=door,
            room=room,
            pause=pauses.append,
        )
        self.assertEqual(pauses, [60])
        self.assertEqual(result.endpoint_creates, 2)
        self.assertEqual(result.endpoint_deletes, 2)
        self.assertEqual(result_by_id(result)["m1"].outcome, Outcome.PASS)

    def test_grades_finished_before_the_zone_dies_still_count(self):
        door = FakeDoor(["available", "available"])
        room = ScriptedRoom(
            [RoomResult.PASS, RoomResult.ZONE_DOWN, RoomResult.FAIL, RoomResult.PASS]
        )
        quotas: dict[str, Quota] = {}
        result = self.run_batch(
            [
                Submission("a@example.com", "done"),
                Submission("b@example.com", "retry"),
                Submission("c@example.com", "later"),
            ],
            quotas,
            door=door,
            room=room,
        )
        by_id = result_by_id(result)
        self.assertEqual(by_id["done"].outcome, Outcome.PASS)
        self.assertTrue(by_id["done"].counts_toward_cap)
        self.assertEqual(by_id["retry"].outcome, Outcome.FAIL)
        self.assertEqual(by_id["later"].outcome, Outcome.PASS)
        self.assertEqual(result.endpoint_creates, 2)
        self.assertEqual(graded_attempts_on(quotas["a@example.com"], TODAY), 1)
        self.assertEqual(room.graded, ["done", "retry", "retry", "later"])

    def test_a_delete_failure_is_reported_and_does_not_drop_the_grade(self):
        door = FakeDoor()
        door.fail_delete = True
        result = self.run_batch(
            [Submission("a@example.com", "m1")],
            room=ScriptedRoom([RoomResult.PASS]),
            door=door,
        )
        self.assertTrue(result.endpoint_left_open)
        self.assertEqual(result.endpoint_deletes, 0)
        self.assertEqual(result_by_id(result)["m1"].outcome, Outcome.PASS)

    def test_the_door_and_the_role_allow_one_sonnet(self):
        role = room_role_policy(ACCOUNT)
        door_policy = endpoint_policy(ACCOUNT)
        role_resources = set(role["Statement"][0]["Resource"])
        door_resources = set(door_policy["Statement"][0]["Resource"])
        profile = profile_arn(ACCOUNT)
        foundation = {
            f"arn:aws:bedrock:{region}::foundation-model/{FOUNDATION_MODEL_ID}"
            for region in PROFILE_REGIONS
        }
        self.assertEqual(role_resources, {profile, *foundation})
        self.assertEqual(
            door_resources,
            {
                profile,
                f"arn:aws:bedrock:{HOME_REGION}::foundation-model/{FOUNDATION_MODEL_ID}",
            },
        )
        for document in (role, door_policy):
            statement = document["Statement"][0]
            self.assertEqual(statement["Action"], [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:Converse",
                "bedrock:ConverseStream",
            ])
            encoded = json.dumps(document)
            self.assertNotIn("haiku", encoded)
            self.assertNotIn("sonnet-4-5", encoded)
            self.assertNotIn("global.anthropic", encoded)
            self.assertIn(PROFILE_ID, encoded)
        self.assertEqual(
            door_policy["Statement"][0]["Condition"],
            {"StringEquals": {"aws:PrincipalAccount": ACCOUNT}},
        )
        order = door_order(
            account_id=ACCOUNT,
            vpc_id=VPC,
            subnet_id=SUBNET,
            security_group_id=SECURITY_GROUP,
        )
        self.assertEqual(json.loads(order.policy_document), door_policy)

    def test_two_subnets_are_rejected(self):
        order = door_order(
            account_id=ACCOUNT,
            vpc_id=VPC,
            subnet_id=SUBNET,
            security_group_id=SECURITY_GROUP,
        )
        widened = DoorOrder(
            vpc_id=order.vpc_id,
            service_name=order.service_name,
            subnet_ids=(SUBNET, "subnet-b"),
            security_group_ids=order.security_group_ids,
            policy_document=order.policy_document,
        )
        with self.assertRaises(ValueError):
            ec2_create_vpc_endpoint_args(widened)

    def test_a_second_batch_opens_a_new_door(self):
        door = FakeDoor(["available", "available"])
        room = ScriptedRoom([RoomResult.PASS, RoomResult.FAIL])
        first = self.run_batch(
            [Submission("a@example.com", "m1")],
            door=door,
            room=room,
        )
        second = self.run_batch(
            [Submission("b@example.com", "m2")],
            door=door,
            room=room,
        )
        self.assertEqual(first.endpoint_deletes, 1)
        self.assertEqual(second.endpoint_creates, 1)
        self.assertEqual(door.created, ["vpce-1", "vpce-2"])
        self.assertEqual(door.live, 0)


if __name__ == "__main__":
    unittest.main()
