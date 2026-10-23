"""
AWS（DynamoDB・SQS・S3）を moto のモックで確かめる hook。作るのは次の3つ。

- casebook_env: moto でモックの AWS を用意し、テーブル・キュー・バケットを作る
- pytest_casebook_setup: setup: の s3（入力ファイル）と dynamodb（行）を入れ、
  ケースが終わったら空にする
- pytest_casebook_observe: observe: / expect: の dynamodb.<テーブル>・sqs.<キュー>・
  s3.<バケット> の中身を取り出す

call: で関数を同じプロセスで呼ぶので、moto のモックがそのまま効く。command: で別プロセスの
CLI を確かめるときは、moto のサーバーか LocalStack を立て、env: で AWS_ENDPOINT_URL を渡す
（このファイルの hook は、boto3 の接続先が変わるだけでそのまま使える）。

moto が入っていなければ、このディレクトリのサンプルは集めない。
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
    # テーブル名 -> キーの名前
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
        # 本物の AWS に繋がらないよう、ダミーの認証情報にする
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
        # s3: {バケット/キー: 中身}
        for path, text in data.get("s3", {}).items():
            bucket, _, key = path.partition("/")
            env.s3.put_object(Bucket=bucket, Key=key, Body=text.encode())
        # dynamodb: {テーブル: [行, ...]}
        for table, items in data.get("dynamodb", {}).items():
            for item in items:
                env.dynamodb.Table(table).put_item(Item=item)
        return _emptied(env)

    @contextlib.contextmanager
    def _emptied(env: Aws) -> Iterator[None]:
        """ケースが終わったら、テーブル・キュー・バケットを空にする（次のケースに残さない）。"""
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
            # scan の順は決まっていないので、キーで並べる
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
        キューのメッセージをすべて受け取って消す（1回で受け取れるのは 10 件まで）。

        消さないと、見えない時間（visibility timeout）が過ぎたあとに次のケースで見えてしまう。
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
        """DynamoDB の数値（Decimal）を int / float にする（YAML の数と比べられるように）。"""
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        if isinstance(value, dict):
            return {k: _plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_plain(v) for v in value]
        return value
