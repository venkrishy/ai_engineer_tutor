"""Lambda entry point: a letter saved in S3 becomes a reply."""

from __future__ import annotations

import json
import os
from urllib.parse import unquote_plus

import boto3

from tutor.mail import REGION, SesMail, ses_sending
from tutor.rooms import NullDoor, UngradedRoom
from tutor.service import handle
from tutor.store import DynamoItems, Store

RAW_PREFIX = "raw/"
SES_SETUP_NOTE = "AMAZON_SES_SETUP_NOTIFICATION"


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    sesv2 = boto3.client("sesv2", region_name=REGION)
    table = boto3.resource("dynamodb", region_name=REGION).Table(os.environ["TABLE_NAME"])
    store = Store(DynamoItems(table))
    mail = SesMail(sesv2)
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith(RAW_PREFIX) or key.endswith(SES_SETUP_NOTE):
            continue
        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        result = handle(
            raw,
            store=store,
            mail=mail,
            door=NullDoor(),
            room=UngradedRoom(),
            ses=ses_sending(sesv2),
        )
        print(json.dumps({"key": key, "result": result}))
