"""Upload an assignment folder to the catalog: python3 scripts/upload_assignment.py assignments/triage"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tutor.catalog import BundleError, S3Blobs, parse_bundle, save_bundle
from tutor.store import DynamoItems

REGION = "us-east-1"
TABLE = "tutor-main"
BUCKET = "tutor-mail-theaiguru-908196778839"


def zip_folder(folder: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.writestr(path.relative_to(folder).as_posix(), path.read_bytes())
    return buffer.getvalue()


def main(argv: list[str]) -> int:
    folder = Path(argv[1])
    try:
        bundle = parse_bundle(zip_folder(folder))
    except BundleError as error:
        print("The bundle is not valid:")
        for problem in error.problems:
            print(f"  - {problem}")
        return 1
    items = DynamoItems(boto3.resource("dynamodb", region_name=REGION).Table(TABLE))
    blobs = S3Blobs(boto3.client("s3", region_name=REGION), BUCKET)
    version = save_bundle(items, blobs, bundle)
    print(f"Uploaded {bundle.id} version {version} with {len(bundle.levels)} levels.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
