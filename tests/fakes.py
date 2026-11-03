"""In-memory stand-in for the DynamoDB table, with the same rules for conditions."""

from __future__ import annotations


class MemoryItems:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def get(self, pk, sk):
        row = self.rows.get((pk, sk))
        return dict(row) if row else None

    def put(self, item):
        self.rows[(item["PK"], item["SK"])] = dict(item)

    def put_if_absent(self, item):
        key = (item["PK"], item["SK"])
        if key in self.rows:
            return False
        self.rows[key] = dict(item)
        return True

    def put_if_version(self, item, version):
        key = (item["PK"], item["SK"])
        row = self.rows.get(key)
        if row is None or row.get("version") != version:
            return False
        self.rows[key] = dict(item)
        return True

    def delete(self, pk, sk):
        self.rows.pop((pk, sk), None)

    def query(self, pk, sk_prefix=""):
        return [
            dict(row)
            for (p, s), row in sorted(self.rows.items())
            if p == pk and s.startswith(sk_prefix)
        ]

    def scan_sk(self, sk):
        return [dict(row) for (_p, s), row in sorted(self.rows.items()) if s == sk]

    def add(self, pk, sk, field, amount):
        row = self.rows.setdefault((pk, sk), {"PK": pk, "SK": sk})
        row[field] = row.get(field, 0) + amount
        return row[field]
