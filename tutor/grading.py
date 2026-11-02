"""Grade a batch of submissions through one short-lived Bedrock door.

The door is an interface VPC endpoint in a single availability zone. It is
created when a batch has work to grade and deleted before the batch returns.
A zone failure pauses and retries. After the last try, leftover submissions
are not graded and do not spend a daily attempt.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol

PROFILE_ID = "us.anthropic.claude-sonnet-4-6"
FOUNDATION_MODEL_ID = "anthropic.claude-sonnet-4-6"
HOME_REGION = "us-east-1"
PROFILE_REGIONS = ("us-east-1", "us-east-2", "us-west-2")
PHASE_AVAILABILITY_ZONES = 1
DAILY_GRADED_ATTEMPT_CAP = 10
ZONE_TRIES = 3

BEDROCK_ACTIONS = (
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream",
    "bedrock:Converse",
    "bedrock:ConverseStream",
)


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_GRADED = "not_graded"
    CAPPED = "capped"


class RoomResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_GRADED = "not_graded"
    ZONE_DOWN = "zone_down"


@dataclass
class Quota:
    attempt_day: date | None = None
    graded_attempts: int = 0


@dataclass(frozen=True)
class Submission:
    email: str
    message_id: str


@dataclass(frozen=True)
class ItemResult:
    message_id: str
    email: str
    outcome: Outcome
    counts_toward_cap: bool


@dataclass
class BatchResult:
    items: list[ItemResult]
    endpoint_creates: int
    endpoint_deletes: int
    endpoint_left_open: bool = False


@dataclass(frozen=True)
class DoorOrder:
    vpc_id: str
    service_name: str
    subnet_ids: tuple[str, ...]
    security_group_ids: tuple[str, ...]
    policy_document: str
    private_dns: bool = True


class Door(Protocol):
    def start_create(self, order: DoorOrder) -> str: ...

    def status(self, endpoint_id: str) -> str: ...

    def delete(self, endpoint_id: str) -> None: ...


class Room(Protocol):
    def grade(self, submission: Submission) -> RoomResult: ...


def profile_arn(account_id: str, region: str = HOME_REGION) -> str:
    return (
        f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{PROFILE_ID}"
    )


def foundation_arn(region: str) -> str:
    return f"arn:aws:bedrock:{region}::foundation-model/{FOUNDATION_MODEL_ID}"


def sonnet_invoke_statement(account_id: str) -> dict:
    """Allow this Sonnet profile and the three regional models it routes to."""
    resources = [profile_arn(account_id), *[foundation_arn(region) for region in PROFILE_REGIONS]]
    return {
        "Sid": "InvokeOneSonnet",
        "Effect": "Allow",
        "Action": list(BEDROCK_ACTIONS),
        "Resource": resources,
    }


def room_role_policy(account_id: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [sonnet_invoke_statement(account_id)],
    }


def endpoint_policy(account_id: str) -> dict:
    """The door only accepts this Sonnet profile in the home region."""
    statement = sonnet_invoke_statement(account_id)
    statement["Principal"] = "*"
    statement["Resource"] = [
        profile_arn(account_id, HOME_REGION),
        foundation_arn(HOME_REGION),
    ]
    statement["Condition"] = {"StringEquals": {"aws:PrincipalAccount": account_id}}
    return {"Version": "2012-10-17", "Statement": [statement]}


def door_order(
    *,
    account_id: str,
    vpc_id: str,
    subnet_id: str,
    security_group_id: str,
) -> DoorOrder:
    if PHASE_AVAILABILITY_ZONES != 1:
        raise RuntimeError("this phase creates the door in one zone")
    return DoorOrder(
        vpc_id=vpc_id,
        service_name=f"com.amazonaws.{HOME_REGION}.bedrock-runtime",
        subnet_ids=(subnet_id,),
        security_group_ids=(security_group_id,),
        policy_document=json.dumps(endpoint_policy(account_id), separators=(",", ":")),
        private_dns=True,
    )


def ec2_create_vpc_endpoint_args(order: DoorOrder) -> dict:
    if len(order.subnet_ids) != PHASE_AVAILABILITY_ZONES:
        raise ValueError("the door must be created in one availability zone")
    return {
        "VpcId": order.vpc_id,
        "VpcEndpointType": "Interface",
        "ServiceName": order.service_name,
        "SubnetIds": list(order.subnet_ids),
        "SecurityGroupIds": list(order.security_group_ids),
        "PolicyDocument": order.policy_document,
        "PrivateDnsEnabled": order.private_dns,
    }


def graded_attempts_on(quota: Quota, today: date) -> int:
    if quota.attempt_day != today:
        return 0
    return quota.graded_attempts


def mark_graded(quota: Quota, today: date) -> None:
    if quota.attempt_day != today:
        quota.attempt_day = today
        quota.graded_attempts = 0
    quota.graded_attempts += 1


def run_batch(
    waiting: Sequence[Submission],
    quotas: dict[str, Quota],
    *,
    door: Door,
    room: Room,
    today: date,
    account_id: str,
    vpc_id: str,
    subnet_id: str,
    security_group_id: str,
    arrive: Callable[[], Sequence[Submission]] | None = None,
    pause: Callable[[float], None] = lambda _seconds: None,
    create_timeout_s: float = 8 * 60,
    poll_interval_s: float = 15,
    retry_pause_s: tuple[float, ...] = (60, 120),
) -> BatchResult:
    order = door_order(
        account_id=account_id,
        vpc_id=vpc_id,
        subnet_id=subnet_id,
        security_group_id=security_group_id,
    )
    seen: dict[str, Submission] = {}
    results: list[ItemResult] = []
    finished: set[str] = set()
    pending: list[Submission] = []

    def ingest(subs: Sequence[Submission]) -> None:
        for sub in subs:
            if sub.message_id in seen:
                continue
            seen[sub.message_id] = sub
            quota = quotas.setdefault(sub.email, Quota())
            if graded_attempts_on(quota, today) >= DAILY_GRADED_ATTEMPT_CAP:
                results.append(
                    ItemResult(sub.message_id, sub.email, Outcome.CAPPED, False)
                )
                finished.add(sub.message_id)
            else:
                pending.append(sub)

    ingest(waiting)
    if arrive is not None:
        ingest(arrive())
    if not pending:
        return BatchResult(results, 0, 0)

    creates = 0
    deletes = 0
    left_open = False
    max_polls = max(1, int(create_timeout_s / poll_interval_s))

    def wait_until_available(endpoint_id: str) -> bool:
        polls = 0
        while True:
            status = door.status(endpoint_id)
            if status == "available":
                return True
            if status != "pending":
                return False
            if arrive is not None:
                ingest(arrive())
            polls += 1
            if polls >= max_polls:
                return False
            pause(poll_interval_s)

    def close(endpoint_id: str | None) -> None:
        nonlocal deletes, left_open
        if endpoint_id is None:
            return
        try:
            door.delete(endpoint_id)
        except Exception:
            left_open = True
            return
        deletes += 1

    for attempt in range(1, ZONE_TRIES + 1):
        endpoint_id: str | None = None
        zone_down = False
        completed = False
        try:
            endpoint_id = door.start_create(order)
            creates += 1
            if not wait_until_available(endpoint_id):
                zone_down = True
            else:
                for sub in list(pending):
                    if sub.message_id in finished:
                        continue
                    quota = quotas.setdefault(sub.email, Quota())
                    if graded_attempts_on(quota, today) >= DAILY_GRADED_ATTEMPT_CAP:
                        results.append(
                            ItemResult(sub.message_id, sub.email, Outcome.CAPPED, False)
                        )
                        finished.add(sub.message_id)
                        continue
                    try:
                        room_result = room.grade(sub)
                    except Exception:
                        zone_down = True
                        break
                    if room_result is RoomResult.ZONE_DOWN:
                        zone_down = True
                        break
                    if room_result in (RoomResult.PASS, RoomResult.FAIL):
                        mark_graded(quota, today)
                        outcome = (
                            Outcome.PASS
                            if room_result is RoomResult.PASS
                            else Outcome.FAIL
                        )
                        results.append(
                            ItemResult(sub.message_id, sub.email, outcome, True)
                        )
                    else:
                        results.append(
                            ItemResult(
                                sub.message_id, sub.email, Outcome.NOT_GRADED, False
                            )
                        )
                    finished.add(sub.message_id)
                if not zone_down:
                    completed = True
        except Exception:
            zone_down = True
        finally:
            close(endpoint_id)

        if completed:
            break
        if attempt == ZONE_TRIES:
            for sub in pending:
                if sub.message_id in finished:
                    continue
                results.append(
                    ItemResult(sub.message_id, sub.email, Outcome.NOT_GRADED, False)
                )
                finished.add(sub.message_id)
            break
        pause(retry_pause_s[min(attempt - 1, len(retry_pause_s) - 1)])
        pending = [sub for sub in pending if sub.message_id not in finished]

    return BatchResult(results, creates, deletes, left_open)


def result_by_id(result: BatchResult) -> dict[str, ItemResult]:
    return {item.message_id: item for item in result.items}
