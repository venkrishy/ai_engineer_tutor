"""Assignments, their levels, and the files that grade them.

An assignment is uploaded as one zip bundle:

  assignment.json                  {"id": "triage", "name": "Triage tickets", "order": 1}
  levels/01-classify/level.json    {"name": "Classify", "title": "Classify incoming support tickets"}
  levels/01-classify/context.md    optional: the story around the level
  levels/01-classify/instructions.md   what the student will build, in a sentence or two
  levels/01-classify/prompt.md     the one-shot prompt the student pastes into their coding tool
  levels/01-classify/rubric.md     optional: what the note writer should look for
  levels/01-classify/tickets.json  five {"input": {...}, "expected": {...}, "good": {...}}
                                   ("good" is a full right answer, only needed when the
                                   expected fields alone are not one)
  levels/01-classify/checker.py    optional: check(ticket, output) -> list of problems

Instructions and the order live in DynamoDB. The hidden tickets and the checker
live in S3, and only the grader reads them.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Callable, Protocol

from tutor.clerk import Level

TICKETS_PER_LEVEL = 5
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_FILES = 100
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


class Blobs(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...


class S3Blobs:
    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()


class BundleError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


LEVEL_TEXT_FIELDS = ("title", "context", "instructions", "prompt", "rubric")
TEMPLATE_NAMES = ("welcome", "steps", "next")


@dataclass(frozen=True)
class LevelFiles:
    name: str
    instructions: str
    tickets: list[dict]
    checker: str | None
    title: str = ""
    context: str = ""
    prompt: str = ""
    rubric: str = ""


@dataclass(frozen=True)
class Bundle:
    id: str
    name: str
    order: int
    levels: tuple[LevelFiles, ...]


@dataclass(frozen=True)
class LevelAssets:
    tickets: list[dict]
    checker: Callable[[dict, dict], list[str]]


def match_expected(ticket: dict, output: dict) -> list[str]:
    """The default checker: every expected field must match, and the id must come back."""
    problems = []
    if output.get("id") != ticket["input"]["id"]:
        problems.append("id is missing or wrong")
    for field, value in ticket["expected"].items():
        if output.get(field) != value:
            problems.append(f"{field} does not match the rules")
    return problems


def compile_checker(source: str | None) -> Callable[[dict, dict], list[str]]:
    if source is None:
        return match_expected
    namespace: dict = {"__name__": "checker"}
    exec(compile(source, "checker.py", "exec"), namespace)
    return namespace["check"]


def _read_zip(data: bytes) -> dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BundleError(["the upload is not a zip"])
    infos = [info for info in archive.infolist() if not info.is_dir()]
    if len(infos) > MAX_BUNDLE_FILES:
        raise BundleError([f"more than {MAX_BUNDLE_FILES} files"])
    if sum(info.file_size for info in infos) > MAX_BUNDLE_BYTES:
        raise BundleError(["the bundle is larger than 2 MB unpacked"])
    files = {}
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in name.split("/") or name.startswith("__MACOSX/"):
            continue
        files[name] = archive.read(info)
    top = {name.split("/")[0] for name in files}
    if "assignment.json" not in files and len(top) == 1:
        prefix = next(iter(top)) + "/"
        files = {name[len(prefix):]: body for name, body in files.items()}
    return files


def parse_bundle(data: bytes) -> Bundle:
    files = _read_zip(data)
    problems: list[str] = []

    def load_json(name: str):
        try:
            return json.loads(files[name].decode())
        except KeyError:
            problems.append(f"{name} is missing")
        except (ValueError, UnicodeDecodeError):
            problems.append(f"{name} is not valid JSON")
        return None

    meta = load_json("assignment.json")
    assignment_id, assignment_name, order = "", "", 0
    if isinstance(meta, dict):
        assignment_id = str(meta.get("id", ""))
        assignment_name = str(meta.get("name", "")).strip()
        order = meta.get("order")
        if not ID_PATTERN.match(assignment_id):
            problems.append("assignment.json id must be lowercase letters, digits, and dashes")
        if not assignment_name:
            problems.append("assignment.json name is empty")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            problems.append("assignment.json order must be a whole number from 1")
    elif meta is not None:
        problems.append("assignment.json must be an object")

    folders = sorted(
        {name.split("/")[1] for name in files if name.startswith("levels/") and name.count("/") >= 2}
    )
    if not folders:
        problems.append("there are no levels")
    levels: list[LevelFiles] = []
    seen: set[str] = set()
    for folder in folders:
        base = f"levels/{folder}/"
        info = load_json(base + "level.json")
        name = str(info.get("name", "")).strip() if isinstance(info, dict) else ""
        if info is not None and not name:
            problems.append(f"{base}level.json name is empty")
        if name in seen:
            problems.append(f"two levels are named {name}")
        seen.add(name)
        def text(name: str) -> str:
            return files.get(base + name, b"").decode(errors="replace").strip()

        instructions = text("instructions.md")
        if not instructions:
            problems.append(f"{base}instructions.md is missing or empty")
        prompt = text("prompt.md")
        if not prompt:
            problems.append(f"{base}prompt.md is missing or empty")
        title = str(info.get("title", "")).strip() if isinstance(info, dict) else ""
        tickets = load_json(base + "tickets.json")
        if tickets is not None:
            problems.extend(f"{base}tickets.json: {item}" for item in _ticket_problems(tickets))
        checker = files.get(base + "checker.py")
        source = checker.decode(errors="replace") if checker is not None else None
        if isinstance(tickets, list) and not _ticket_problems(tickets):
            problems.extend(f"{base}checker.py: {item}" for item in _checker_problems(source, tickets))
        levels.append(
            LevelFiles(
                name,
                instructions,
                tickets if isinstance(tickets, list) else [],
                source,
                title,
                text("context.md"),
                prompt,
                text("rubric.md"),
            )
        )
    if problems:
        raise BundleError(problems)
    return Bundle(assignment_id, assignment_name, order, tuple(levels))


def _ticket_problems(tickets) -> list[str]:
    if not isinstance(tickets, list) or len(tickets) != TICKETS_PER_LEVEL:
        return [f"needs exactly {TICKETS_PER_LEVEL} tickets"]
    problems = []
    for number, ticket in enumerate(tickets, start=1):
        valid = (
            isinstance(ticket, dict)
            and isinstance(ticket.get("input"), dict)
            and isinstance(ticket["input"].get("id"), str)
            and isinstance(ticket.get("expected"), dict)
        )
        if not valid:
            problems.append(f"ticket {number} needs an input with an id and an expected object")
    return problems


def _checker_problems(source: str | None, tickets: list[dict]) -> list[str]:
    try:
        check = compile_checker(source)
    except Exception as error:
        return [f"does not load: {error}"]
    if not callable(check):
        return ["has no check function"]
    try:
        for ticket in tickets:
            good = ticket.get("good") or dict(ticket["expected"], id=ticket["input"]["id"])
            if check(ticket, good):
                return ["rejects the expected answer"]
        if not check(tickets[0], {}):
            return ["accepts an empty answer"]
    except Exception as error:
        return [f"crashed on a sample: {error}"]
    return []


def save_bundle(items, blobs: Blobs, bundle: Bundle) -> int:
    pk = f"ASSIGNMENT#{bundle.id}"
    old = items.get(pk, "META")
    version = int(old["version"]) + 1 if old else 1
    for position, level in enumerate(bundle.levels, start=1):
        prefix = f"assignments/{bundle.id}/v{version}/{position:02d}"
        blobs.put(f"{prefix}/tickets.json", json.dumps(level.tickets).encode())
        item = {
            "PK": pk,
            "SK": f"LEVEL#{position:02d}",
            "name": level.name,
            "title": level.title,
            "context": level.context,
            "instructions": level.instructions,
            "prompt": level.prompt,
            "rubric": level.rubric,
            "tickets_key": f"{prefix}/tickets.json",
        }
        if level.checker is not None:
            blobs.put(f"{prefix}/checker.py", level.checker.encode())
            item["checker_key"] = f"{prefix}/checker.py"
        items.put(item)
    for stale in items.query(pk, "LEVEL#"):
        if int(stale["SK"].split("#")[1]) > len(bundle.levels):
            items.delete(pk, stale["SK"])
    items.put(
        {
            "PK": pk,
            "SK": "META",
            "id": bundle.id,
            "name": bundle.name,
            "order": bundle.order,
            "version": version,
            "level_count": len(bundle.levels),
        }
    )
    return version


def assignments(items) -> list[dict]:
    metas = [row for row in items.scan_sk("META") if row["PK"].startswith("ASSIGNMENT#")]
    return sorted(metas, key=lambda row: int(row["order"]))


def load_ladder(items) -> tuple[Level, ...]:
    ladder: list[Level] = []
    for meta in assignments(items):
        for row in sorted(items.query(meta["PK"], "LEVEL#"), key=lambda row: row["SK"]):
            ladder.append(
                Level(
                    row["name"],
                    row["instructions"],
                    meta["id"],
                    row.get("title", ""),
                    row.get("context", ""),
                    row.get("prompt", ""),
                    row.get("rubric", ""),
                    meta["name"],
                )
            )
    return tuple(ladder)


def update_level(items, assignment_id: str, position: int, fields: dict) -> list[str]:
    """Change the words of one level. Returns what is wrong, or an empty list when saved."""
    row = items.get(f"ASSIGNMENT#{assignment_id}", f"LEVEL#{position:02d}")
    if row is None:
        return ["no such level"]
    unknown = sorted(set(fields) - set(LEVEL_TEXT_FIELDS))
    if unknown:
        return [f"unknown field {name}" for name in unknown]
    changed = dict(row)
    changed.update({name: str(value).strip() for name, value in fields.items()})
    problems = [f"{name} cannot be empty" for name in ("instructions", "prompt") if not changed.get(name)]
    if problems:
        return problems
    items.put(changed)
    return []


def load_templates(items, defaults: dict[str, str]) -> dict[str, str]:
    templates = dict(defaults)
    for name in TEMPLATE_NAMES:
        row = items.get(f"TEMPLATE#{name}", "TEXT")
        if row and row.get("text", "").strip():
            templates[name] = row["text"]
    return templates


def save_template(items, name: str, text: str) -> list[str]:
    if name not in TEMPLATE_NAMES:
        return [f"unknown template {name}"]
    if not text.strip():
        return ["the text cannot be empty"]
    items.put({"PK": f"TEMPLATE#{name}", "SK": "TEXT", "text": text})
    return []


def load_assets(items, blobs: Blobs, assignment_id: str, level_name: str) -> LevelAssets:
    for row in items.query(f"ASSIGNMENT#{assignment_id}", "LEVEL#"):
        if row["name"] == level_name:
            tickets = json.loads(blobs.get(row["tickets_key"]))
            source = blobs.get(row["checker_key"]).decode() if "checker_key" in row else None
            return LevelAssets(tickets, compile_checker(source))
    raise LookupError(f"{assignment_id}/{level_name}")
