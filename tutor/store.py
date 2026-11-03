"""Keep student cards, handled letters, and history in one DynamoDB table.

One table, keyed by PK and SK:
  STUDENT#<email> / CARD                   the student card
  STUDENT#<email> / EVENT#<time>#<id>      one line of history
  MSG#<message id> / MSG                   a letter someone has claimed
  GLOBALDAY#<date> / TRIES                 graded tries across all students
  SETTINGS / GLOBAL                        switches the admin sets
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol

from collections.abc import Sequence

from tutor.clerk import LADDER, Level, StudentCard


class Conflict(Exception):
    """The card changed since it was loaded."""


class Items(Protocol):
    def get(self, pk: str, sk: str) -> dict | None: ...

    def put(self, item: dict) -> None: ...

    def put_if_absent(self, item: dict) -> bool: ...

    def put_if_version(self, item: dict, version: int) -> bool: ...

    def delete(self, pk: str, sk: str) -> None: ...

    def query(self, pk: str, sk_prefix: str = "") -> list[dict]: ...

    def scan_sk(self, sk: str) -> list[dict]: ...

    def add(self, pk: str, sk: str, field: str, amount: int) -> int: ...


class DynamoItems:
    def __init__(self, table) -> None:
        self._table = table

    def get(self, pk: str, sk: str) -> dict | None:
        return self._table.get_item(Key={"PK": pk, "SK": sk}).get("Item")

    def put(self, item: dict) -> None:
        self._table.put_item(Item=item)

    def put_if_absent(self, item: dict) -> bool:
        return self._conditional_put(item, "attribute_not_exists(PK)", None)

    def put_if_version(self, item: dict, version: int) -> bool:
        return self._conditional_put(item, "version = :v", {":v": version})

    def _conditional_put(self, item, condition, values) -> bool:
        kwargs = {"Item": item, "ConditionExpression": condition}
        if values:
            kwargs["ExpressionAttributeValues"] = values
        try:
            self._table.put_item(**kwargs)
        except self._table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def delete(self, pk: str, sk: str) -> None:
        self._table.delete_item(Key={"PK": pk, "SK": sk})

    def query(self, pk: str, sk_prefix: str = "") -> list[dict]:
        from boto3.dynamodb.conditions import Key

        condition = Key("PK").eq(pk)
        if sk_prefix:
            condition = condition & Key("SK").begins_with(sk_prefix)
        items: list[dict] = []
        kwargs = {"KeyConditionExpression": condition}
        while True:
            page = self._table.query(**kwargs)
            items.extend(page["Items"])
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def scan_sk(self, sk: str) -> list[dict]:
        from boto3.dynamodb.conditions import Attr

        items: list[dict] = []
        kwargs = {"FilterExpression": Attr("SK").eq(sk)}
        while True:
            page = self._table.scan(**kwargs)
            items.extend(page["Items"])
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def add(self, pk: str, sk: str, field: str, amount: int) -> int:
        result = self._table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression="ADD #f :n",
            ExpressionAttributeNames={"#f": field},
            ExpressionAttributeValues={":n": amount},
            ReturnValues="UPDATED_NEW",
        )
        return int(result["Attributes"][field])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, items: Items) -> None:
        self._items = items
        self._versions: dict[str, int] = {}

    def load_card(self, email: str) -> StudentCard | None:
        item = self._items.get(f"STUDENT#{email}", "CARD")
        if item is None:
            self._versions.pop(email, None)
            return None
        self._versions[email] = int(item["version"])
        graded_day = item.get("graded_day")
        return StudentCard(
            email=email,
            assignment_id=item.get("assignment_id", "triage"),
            open_level=item.get("open_level"),
            in_flight=bool(item.get("in_flight", False)),
            graded_tries_today=int(item.get("graded_tries_today", 0)),
            graded_day=date.fromisoformat(graded_day) if graded_day else None,
            last_result=item.get("last_result"),
            finished=bool(item.get("finished", False)),
            registered_at=item.get("registered_at"),
            last_letter_at=item.get("last_letter_at"),
            fails_on_level=int(item.get("fails_on_level", 0)),
        )

    def save_card(self, card: StudentCard, ladder: Sequence[Level] = LADDER) -> None:
        now = _now()
        card.registered_at = card.registered_at or now
        card.last_letter_at = now
        item = {
            "PK": f"STUDENT#{card.email}",
            "SK": "CARD",
            "email": card.email,
            "assignment_id": card.assignment_id,
            "level_index": card.level_index(ladder),
            "level_count": sum(1 for level in ladder if level.assignment == card.assignment_id),
            "in_flight": card.in_flight,
            "graded_tries_today": card.graded_tries_today,
            "finished": card.finished,
            "registered_at": card.registered_at,
            "last_letter_at": card.last_letter_at,
            "fails_on_level": card.fails_on_level,
            "version": self._versions.get(card.email, -1) + 1,
        }
        for name in ("open_level", "last_result"):
            if getattr(card, name) is not None:
                item[name] = getattr(card, name)
        if card.graded_day is not None:
            item["graded_day"] = card.graded_day.isoformat()
        if card.email in self._versions:
            written = self._items.put_if_version(item, self._versions[card.email])
        else:
            written = self._items.put_if_absent(item)
        if not written:
            raise Conflict(card.email)
        self._versions[card.email] = item["version"]

    def claim(self, message_id: str, email: str) -> bool:
        return self._items.put_if_absent(
            {"PK": f"MSG#{message_id}", "SK": "MSG", "email": email, "at": _now()}
        )

    def release(self, message_id: str) -> None:
        self._items.delete(f"MSG#{message_id}", "MSG")

    def record_event(self, email: str, message_id: str, kind: str, detail: str = "") -> None:
        now = _now()
        self._items.put(
            {
                "PK": f"STUDENT#{email}",
                "SK": f"EVENT#{now}#{kind}#{message_id}",
                "kind": kind,
                "message_id": message_id,
                "at": now,
                "detail": detail[:2000],
            }
        )

    def events(self, email: str) -> list[dict]:
        return self._items.query(f"STUDENT#{email}", "EVENT#")

    def cards(self) -> list[dict]:
        return self._items.scan_sk("CARD")

    def delete_student(self, email: str) -> None:
        for row in self._items.query(f"STUDENT#{email}"):
            self._items.delete(row["PK"], row["SK"])
        self._versions.pop(email, None)

    def settings(self) -> dict:
        return self._items.get("SETTINGS", "GLOBAL") or {}

    def set_setting(self, name: str, value) -> None:
        item = self.settings()
        item.update({"PK": "SETTINGS", "SK": "GLOBAL", name: value})
        self._items.put(item)

    def global_tries(self, day: date) -> int:
        item = self._items.get(f"GLOBALDAY#{day.isoformat()}", "TRIES")
        return int(item["count"]) if item else 0

    def add_global_tries(self, day: date, amount: int = 1) -> int:
        return self._items.add(f"GLOBALDAY#{day.isoformat()}", "TRIES", "count", amount)
