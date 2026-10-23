"""
Hooks that check AWS (DynamoDB, SQS, S3) with moto's mock. You write these three:

- casebook_env: start the mock AWS with moto and create the tables, queues and buckets
- pytest_casebook_setup: put the s3 (input files) and dynamodb (rows) of setup: in, and empty
  everything when the case ends
- pytest_casebook_observe: read dynamodb.<table>, sqs.<queue> and s3.<bucket> written in
  observe: / expect:

call: runs the function in this process, so moto's mock applies as is. To check a CLI in a
subprocess with command:, start moto's server or LocalStack and pass AWS_ENDPOINT_URL with env:
(the hooks in this file work unchanged; only where boto3 connects changes).

If moto is not installed, the samples in this directory are not collected.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest

if importlib.util.find_spec("moto") is None:
    collect_ignore_glob = ["*.yaml"]
else:
    import boto3
    from moto import mock_aws

    REGION = "ap-northeast-1"
    # table name -> key name
    TABLES = {"orders": "id"}
    QUEUES = ["order-events"]
    BUCKETS = ["inbox", "reports"]

    @dataclass
    class Aws:
        s3: Any
        sqs: Any
        dynamodb: Any

    @pytest.fixture(scope="session")
    def casebook_env() -> Iterator[Aws]:
        # Dummy credentials, so that nothing reaches the real AWS
        fake = {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": REGION,
        }
        with mock.patch.dict(os.environ, fake), mock_aws():
            aws = Aws(boto3.client("s3"), boto3.client("sqs"), boto3.resource("dynamodb"))
            for table, key in TABLES.items():
                aws.dynamodb.create_table(
                    TableName=table,
                    KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
            for queue in QUEUES:
                aws.sqs.create_queue(QueueName=queue)
            for bucket in BUCKETS:
                aws.s3.create_bucket(
                    Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION}
                )
            yield aws

    def pytest_casebook_setup(data: dict[str, Any], env: Aws) -> Any:
        # s3: {bucket/key: contents}
        for path, text in data.get("s3", {}).items():
            bucket, _, key = path.partition("/")
            env.s3.put_object(Bucket=bucket, Key=key, Body=text.encode())
        # dynamodb: {table: [row, ...]}
        for table, items in data.get("dynamodb", {}).items():
            for item in items:
                env.dynamodb.Table(table).put_item(Item=item)
        return _emptied(env)

    @contextlib.contextmanager
    def _emptied(env: Aws) -> Iterator[None]:
        """Empty the tables, queues and buckets when the case ends (nothing is left over)."""
        try:
            yield
        finally:
            for table, key in TABLES.items():
                for item in env.dynamodb.Table(table).scan()["Items"]:
                    env.dynamodb.Table(table).delete_item(Key={key: item[key]})
            for queue in QUEUES:
                _receive_all(env.sqs, queue)
            for bucket in BUCKETS:
                for obj in env.s3.list_objects_v2(Bucket=bucket).get("Contents", []):
                    env.s3.delete_object(Bucket=bucket, Key=obj["Key"])

    def pytest_casebook_observe(target: str, env: Aws) -> Any:
        kind, _, name = target.partition(".")
        if kind == "dynamodb":
            items = [_plain(item) for item in env.dynamodb.Table(name).scan()["Items"]]
            # the order of scan is not defined, so sort by the key
            return sorted(items, key=lambda item: item[TABLES[name]])
        if kind == "sqs":
            bodies = [json.loads(m["Body"]) for m in _receive_all(env.sqs, name)]
            return sorted(bodies, key=lambda body: json.dumps(body, sort_keys=True))
        if kind == "s3":
            objects = env.s3.list_objects_v2(Bucket=name).get("Contents", [])
            return [
                {
                    "key": obj["Key"],
                    "body": env.s3.get_object(Bucket=name, Key=obj["Key"])["Body"]
                    .read()
                    .decode("utf-8"),
                }
                for obj in sorted(objects, key=lambda obj: obj["Key"])
            ]
        return None

    def _receive_all(sqs: Any, queue: str) -> list[dict[str, Any]]:
        """
        Receive and delete every message in the queue (at most 10 per call).

        Messages that are not deleted become visible again after the visibility timeout, in a
        later case.
        """
        url = sqs.get_queue_url(QueueName=queue)["QueueUrl"]
        messages: list[dict[str, Any]] = []
        while batch := sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get(
            "Messages", []
        ):
            messages += batch
            for message in batch:
                sqs.delete_message(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"])
        return messages

    def _plain(value: Any) -> Any:
        """Turn DynamoDB numbers (Decimal) into int / float, to compare with YAML numbers."""
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        if isinstance(value, dict):
            return {k: _plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_plain(v) for v in value]
        return value
