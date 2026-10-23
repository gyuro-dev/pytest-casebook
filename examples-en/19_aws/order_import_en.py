"""
The function under test (importing orders with AWS).

It reads a CSV from S3, saves the orders in DynamoDB, notifies SQS, and writes a report to S3.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import boto3

TABLE = "orders"
QUEUE = "order-events"
REPORT_BUCKET = "reports"


def import_orders(bucket: str, key: str) -> dict[str, Any]:
    """Import the orders in an S3 CSV (id,price). If a price is not a number, change nothing."""
    s3 = boto3.client("s3")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(body)))
    for row in rows:
        if not row["price"].isdigit():
            raise ValueError(f"price is not a number: {row['id']}")

    table = boto3.resource("dynamodb").Table(TABLE)
    for row in rows:
        table.put_item(Item={"id": row["id"], "price": int(row["price"])})
    sqs = boto3.client("sqs")
    sqs.send_message(
        QueueUrl=sqs.get_queue_url(QueueName=QUEUE)["QueueUrl"],
        MessageBody=json.dumps({"type": "imported", "count": len(rows)}),
    )
    s3.put_object(
        Bucket=REPORT_BUCKET,
        Key=f"{key}.report.txt",
        Body=f"imported {len(rows)} orders".encode(),
    )
    return {"imported": len(rows)}
