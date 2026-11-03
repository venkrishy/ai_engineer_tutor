"""Lambda entry point for the admin dashboard (a Lambda function URL)."""

from __future__ import annotations

import os

import boto3

from tutor.admin import AdminApp, S3Letters, from_function_url, to_function_url
from tutor.catalog import S3Blobs
from tutor.store import DynamoItems, Store

REGION = "us-east-1"
_app: AdminApp | None = None


def _build() -> AdminApp:
    secrets = boto3.client("secretsmanager", region_name=REGION)
    password = secrets.get_secret_value(SecretId=os.environ["PASSWORD_SECRET"])["SecretString"]
    items = DynamoItems(boto3.resource("dynamodb", region_name=REGION).Table(os.environ["TABLE_NAME"]))
    s3 = boto3.client("s3", region_name=REGION)
    bucket = os.environ["MAIL_BUCKET"]
    return AdminApp(Store(items), items, S3Blobs(s3, bucket), S3Letters(s3, bucket), password)


def lambda_handler(event, context):
    global _app
    if _app is None:
        _app = _build()
    return to_function_url(_app.handle(from_function_url(event)))
