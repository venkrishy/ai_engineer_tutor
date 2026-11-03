"""The admin dashboard: one page and a small JSON API behind a password.

The password sits in Secrets Manager. A correct password sets a signed cookie
that lasts eight hours. Nothing but the page itself is served without it.
"""

from __future__ import annotations

import base64
import email
import email.policy
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from tutor.catalog import BundleError, Blobs, assignments, parse_bundle, save_bundle
from tutor.service import GLOBAL_DAILY_CAP
from tutor.store import Store

SESSION_SECONDS = 8 * 60 * 60
LETTERS_SHOWN = 25
PAGE = Path(__file__).with_name("admin_page.html")


class Letters(Protocol):
    def recent(self, limit: int) -> list[dict]: ...

    def read(self, key: str) -> bytes: ...


class S3Letters:
    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def recent(self, limit: int) -> list[dict]:
        rows: list[dict] = []
        pager = self._client.get_paginator("list_objects_v2")
        for page in pager.paginate(Bucket=self._bucket, Prefix="raw/"):
            rows.extend(page.get("Contents", []))
        rows.sort(key=lambda row: row["LastModified"], reverse=True)
        return [
            {"key": row["Key"], "at": row["LastModified"].isoformat(), "size": row["Size"]}
            for row in rows[:limit]
        ]

    def read(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()


@dataclass
class Request:
    method: str
    path: str
    cookie: str = ""
    body: bytes = b""


@dataclass
class Response:
    status: int
    body: bytes | str = b""
    content_type: str = "application/json"
    cookie: str | None = None


def _json(status: int, value) -> Response:
    return Response(status, json.dumps(value, default=str))


def parse_letter(raw: bytes, with_body: bool) -> dict:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    attachments = [
        {"name": part.get_filename() or "", "bytes": len(part.get_payload(decode=True) or b"")}
        for part in message.walk()
        if part.get_content_disposition() == "attachment"
    ]
    letter = {
        "from": str(message["From"] or ""),
        "to": str(message["To"] or ""),
        "subject": str(message["Subject"] or ""),
        "date": str(message["Date"] or ""),
        "spam": str(message["X-SES-Spam-Verdict"] or ""),
        "virus": str(message["X-SES-Virus-Verdict"] or ""),
        "attachments": attachments,
    }
    if with_body:
        text = message.get_body(preferencelist=("plain",))
        letter["body"] = (text.get_content() if text is not None else "")[:6000]
    return letter


class AdminApp:
    def __init__(self, store: Store, items, blobs: Blobs, letters: Letters, password: str, now=None) -> None:
        self._store = store
        self._items = items
        self._blobs = blobs
        self._letters = letters
        self._password = password
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._key = hashlib.sha256(("session:" + password).encode()).digest()

    def make_cookie(self) -> str:
        expires = str(int(self._now().timestamp()) + SESSION_SECONDS)
        signature = hmac.new(self._key, expires.encode(), hashlib.sha256).hexdigest()
        return f"{expires}.{signature}"

    def _signed_in(self, cookie: str) -> bool:
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name != "session":
                continue
            expires, _, signature = value.partition(".")
            good = hmac.new(self._key, expires.encode(), hashlib.sha256).hexdigest()
            if expires.isdigit() and hmac.compare_digest(signature, good):
                return int(expires) > self._now().timestamp()
        return False

    def handle(self, request: Request) -> Response:
        if request.method == "GET" and request.path == "/":
            return Response(200, PAGE.read_text(), "text/html; charset=utf-8")
        if request.path == "/api/login" and request.method == "POST":
            return self._login(request)
        if not self._signed_in(request.cookie):
            return _json(401, {"error": "sign in"})
        route = (request.method, request.path)
        if route == ("GET", "/api/students"):
            return self._students()
        if request.path.startswith("/api/students/"):
            address = request.path[len("/api/students/"):].lower()
            if request.method == "GET":
                return self._student(address)
            if request.method == "DELETE":
                self._store.delete_student(address)
                return _json(200, {"deleted": address})
        if route == ("GET", "/api/letters"):
            return self._letters_list()
        if request.method == "GET" and request.path.startswith("/api/letter/"):
            key = request.path[len("/api/letter/"):]
            if not key.startswith("raw/"):
                return _json(404, {"error": "no such letter"})
            return _json(200, parse_letter(self._letters.read(key), True))
        if route == ("GET", "/api/assignments"):
            return self._assignments()
        if route == ("POST", "/api/assignments"):
            return self._upload(request.body)
        if route == ("GET", "/api/settings"):
            return self._settings()
        if route == ("POST", "/api/settings"):
            self._store.set_setting("paused", bool(json.loads(request.body or b"{}").get("paused")))
            return self._settings()
        return _json(404, {"error": "not found"})

    def _login(self, request: Request) -> Response:
        try:
            given = str(json.loads(request.body or b"{}").get("password", ""))
        except ValueError:
            given = ""
        if not hmac.compare_digest(given.encode(), self._password.encode()):
            return _json(401, {"error": "wrong password"})
        return Response(200, json.dumps({"ok": True}), cookie=self.make_cookie())

    def _students(self) -> Response:
        rows = sorted(self._store.cards(), key=lambda row: row.get("last_letter_at", ""), reverse=True)
        names = {row["id"]: row["name"] for row in assignments(self._items)}
        for row in rows:
            row["assignment_name"] = names.get(row.get("assignment_id"), row.get("assignment_id"))
        return _json(200, rows)

    def _student(self, address: str) -> Response:
        card = self._items.get(f"STUDENT#{address}", "CARD")
        if card is None:
            return _json(404, {"error": "no such student"})
        return _json(200, {"card": card, "events": self._store.events(address)})

    def _letters_list(self) -> Response:
        rows = []
        for row in self._letters.recent(LETTERS_SHOWN):
            try:
                summary = parse_letter(self._letters.read(row["key"]), False)
            except Exception:
                summary = {}
            rows.append({**row, **summary})
        return _json(200, rows)

    def _assignments(self) -> Response:
        out = []
        for meta in assignments(self._items):
            levels = sorted(self._items.query(meta["PK"], "LEVEL#"), key=lambda row: row["SK"])
            out.append(
                {
                    "id": meta["id"],
                    "name": meta["name"],
                    "order": meta["order"],
                    "version": meta["version"],
                    "levels": [{"name": row["name"], "instructions": row["instructions"]} for row in levels],
                }
            )
        return _json(200, out)

    def _upload(self, body: bytes) -> Response:
        try:
            bundle = parse_bundle(body)
        except BundleError as error:
            return _json(400, {"problems": error.problems})
        version = save_bundle(self._items, self._blobs, bundle)
        return _json(200, {"id": bundle.id, "version": version, "levels": len(bundle.levels)})

    def _settings(self) -> Response:
        today = self._now().date()
        return _json(
            200,
            {
                "paused": bool(self._store.settings().get("paused")),
                "global_tries_today": self._store.global_tries(today),
                "global_cap": GLOBAL_DAILY_CAP,
            },
        )


def from_function_url(event: dict) -> Request:
    http = event["requestContext"]["http"]
    body = event.get("body") or ""
    raw = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode()
    return Request(http["method"], event.get("rawPath", "/"), "; ".join(event.get("cookies") or []), raw)


def to_function_url(response: Response) -> dict:
    out = {
        "statusCode": response.status,
        "headers": {
            "content-type": response.content_type,
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            "content-security-policy": "default-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
        },
        "body": response.body if isinstance(response.body, str) else response.body.decode(),
    }
    if response.cookie:
        out["cookies"] = [f"session={response.cookie}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}"]
    return out
