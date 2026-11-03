"""Lambda entry point: a letter saved in S3 becomes a reply."""

from __future__ import annotations

import json
import os
from urllib.parse import unquote_plus

import boto3

from tutor.catalog import S3Blobs, load_assets, load_ladder
from tutor.clerk import LADDER
from tutor.mail import REGION, SesMail, ses_sending
from tutor.notes import BedrockModel
from tutor.rooms import AgentCoreRoom, NullDoor
from tutor.service import handle
from tutor.store import DynamoItems, Store

RAW_PREFIX = "raw/"
SES_SETUP_NOTE = "AMAZON_SES_SETUP_NOTIFICATION"


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    sesv2 = boto3.client("sesv2", region_name=REGION)
    table = boto3.resource("dynamodb", region_name=REGION).Table(os.environ["TABLE_NAME"])
    items = DynamoItems(table)
    store = Store(items)
    mail = SesMail(sesv2)
    model = BedrockModel(boto3.client("bedrock-runtime", region_name=REGION))
    agentcore = boto3.client("bedrock-agentcore", region_name=REGION)
    ladder = load_ladder(items) or LADDER
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith(RAW_PREFIX) or key.endswith(SES_SETUP_NOTE):
            continue
        blobs = S3Blobs(s3, bucket)

        def make_room(cards, payloads):
            return AgentCoreRoom(
                agentcore,
                cards,
                payloads,
                lambda assignment_id, level: load_assets(items, blobs, assignment_id, level),
            )

        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        result = handle(
            raw,
            store=store,
            mail=mail,
            door=NullDoor(),
            ses=ses_sending(sesv2),
            model=model,
            ladder=ladder,
            make_room=make_room,
        )
        print(json.dumps({"key": key, "result": result}))
