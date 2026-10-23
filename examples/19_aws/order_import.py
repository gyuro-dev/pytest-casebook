"""
確かめる対象の関数（AWS を使う注文の取り込み）。

S3 の CSV を読み、注文を DynamoDB に保存し、SQS に通知して、結果を S3 に書く。
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
    """S3 の CSV（id,price）の注文を取り込む。価格が数字でない行があれば、何もせずに例外にする。"""
    s3 = boto3.client("s3")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(body)))
    for row in rows:
        if not row["price"].isdigit():
            raise ValueError(f"価格が数字ではありません: {row['id']}")

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
        Body=f"{len(rows)} 件を取り込みました".encode(),
    )
    return {"imported": len(rows)}
