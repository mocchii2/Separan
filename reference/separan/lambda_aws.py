"""Narrow AWS service adapter used by Separan Lambda applications.

This module exposes transport and persistence primitives only. Routing,
suppression, templates, and state-transition policy remain Separan code.
"""

import base64
from decimal import Decimal
import gzip
import json
import os
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ElementTree

from .lambda_runtime import HostFunction


def _dynamodb_encode(value):
    if value is None: return {"NULL": True}
    if type(value) is bool: return {"BOOL": value}
    if type(value) in (int, float, Decimal): return {"N": str(value)}
    if type(value) is str: return {"S": value}
    if isinstance(value, bytes): return {"B": value}
    if type(value) is list: return {"L": [_dynamodb_encode(item) for item in value]}
    if type(value) is dict: return {"M": {str(key): _dynamodb_encode(item) for key, item in value.items()}}
    raise TypeError(f"Unsupported DynamoDB value: {type(value).__name__}")


def _dynamodb_decode(value):
    if "NULL" in value: return None
    if "BOOL" in value: return bool(value["BOOL"])
    if "S" in value: return value["S"]
    if "B" in value: return bytes(value["B"])
    if "N" in value:
        number = Decimal(value["N"])
        return int(number) if number == number.to_integral_value() else float(number)
    if "L" in value: return [_dynamodb_decode(item) for item in value["L"]]
    if "M" in value: return {key: _dynamodb_decode(item) for key, item in value["M"].items()}
    raise ValueError("Unknown DynamoDB AttributeValue")


def _dynamodb_item(value):
    return {str(key): _dynamodb_encode(item) for key, item in value.items()}


def _decode_item(value):
    return {key: _dynamodb_decode(item) for key, item in value.items()}


class AwsLambdaAdapter:
    def __init__(self, client_factory=None, environment=None, clock=None, urlopen=None):
        if client_factory is None:
            import boto3
            client_factory = boto3.client
        self.client_factory = client_factory
        self.environment = os.environ if environment is None else environment
        self.clock = time.time if clock is None else clock
        self.urlopen = urllib.request.urlopen if urlopen is None else urlopen
        self._clients = {}

    def client(self, name):
        if name not in self._clients:
            self._clients[name] = self.client_factory(name)
        return self._clients[name]

    def functions(self):
        definitions = (
            ("aws_environment", 1, 2, self.environment_get),
            ("aws_epoch_seconds", 0, 0, self.epoch_seconds),
            ("aws_uuid", 0, 0, self.random_uuid),
            ("aws_sns_publish", 2, 3, self.sns_publish),
            ("aws_s3_read_json", 2, 3, self.s3_read_json),
            ("aws_s3_write_json_if_absent", 3, 3, self.s3_write_json_if_absent),
            ("aws_dynamodb_get", 3, 3, self.dynamodb_get),
            ("aws_dynamodb_put", 2, 2, self.dynamodb_put),
            ("aws_dynamodb_delete", 3, 3, self.dynamodb_delete),
            ("aws_dynamodb_reserve_until", 5, 5, self.dynamodb_reserve_until),
            ("aws_ec2_instance_state", 1, 1, self.ec2_instance_state),
            ("aws_rds_instance_state", 1, 1, self.rds_instance_state),
            ("aws_cloudwatch_logs_decode", 1, 1, self.cloudwatch_logs_decode),
            ("aws_windows_event_parse", 1, 1, self.windows_event_parse),
            ("aws_cloudformation_respond", 3, 4, self.cloudformation_respond),
        )
        return {name: HostFunction(name, minimum, maximum, implementation) for name, minimum, maximum, implementation in definitions}

    def environment_get(self, arguments, named):
        name = arguments[0]
        if type(name) is not str or not name: raise ValueError("environment name must be a non-empty string")
        if name in self.environment: return self.environment[name]
        return arguments[1] if len(arguments) == 2 else None

    def epoch_seconds(self, arguments, named): return int(self.clock())
    def random_uuid(self, arguments, named): return str(uuid.uuid4())

    def sns_publish(self, arguments, named):
        topic, message = arguments[0], arguments[1]
        request = {"TopicArn": topic, "Message": message}
        if len(arguments) == 3 and arguments[2]: request["Subject"] = arguments[2]
        return self.client("sns").publish(**request).get("MessageId")

    @staticmethod
    def _not_found(exc):
        response = getattr(exc, "response", {})
        return response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NoSuchBucket", "NotFound")

    def s3_read_json(self, arguments, named):
        bucket, key = arguments[0], arguments[1]
        default = arguments[2] if len(arguments) == 3 else None
        try:
            body = self.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception as exc:
            if self._not_found(exc): return default
            raise
        return json.loads(body)

    def s3_write_json_if_absent(self, arguments, named):
        bucket, key, value = arguments
        client = self.client("s3")
        try:
            client.head_object(Bucket=bucket, Key=key)
            return False
        except Exception as exc:
            if not self._not_found(exc): raise
        client.put_object(
            Bucket=bucket, Key=key,
            Body=json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json", ServerSideEncryption="AES256",
        )
        return True

    def dynamodb_get(self, arguments, named):
        table, pk, sk = arguments
        response = self.client("dynamodb").get_item(
            TableName=table,
            Key={"pk": {"S": str(pk)}, "sk": {"S": str(sk)}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        return _decode_item(item) if item else None

    def dynamodb_put(self, arguments, named):
        table, item = arguments
        self.client("dynamodb").put_item(TableName=table, Item=_dynamodb_item(item))
        return None

    def dynamodb_delete(self, arguments, named):
        table, pk, sk = arguments
        self.client("dynamodb").delete_item(
            TableName=table,
            Key={"pk": {"S": str(pk)}, "sk": {"S": str(sk)}},
        )
        return None

    def dynamodb_reserve_until(self, arguments, named):
        table, pk, sk, expires_at, now = arguments
        try:
            self.client("dynamodb").put_item(
                TableName=table,
                Item={
                    "pk": {"S": str(pk)}, "sk": {"S": str(sk)},
                    "expires_at": {"N": str(expires_at)},
                },
                ConditionExpression="attribute_not_exists(pk) OR expires_at < :now",
                ExpressionAttributeValues={":now": {"N": str(now)}},
            )
            return True
        except Exception as exc:
            response = getattr(exc, "response", {})
            if response.get("Error", {}).get("Code") == "ConditionalCheckFailedException": return False
            raise

    def ec2_instance_state(self, arguments, named):
        identifier = arguments[0]
        try:
            response = self.client("ec2").describe_instances(InstanceIds=[identifier])
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = response.get("Error", {}).get("Code", "")
            if code in ("InvalidInstanceID.NotFound", "InvalidInstanceID.Malformed"): return "not_found"
            raise
        instances = [
            item
            for reservation in response.get("Reservations", [])
            for item in reservation.get("Instances", [])
        ]
        return instances[0].get("State", {}).get("Name", "unknown") if instances else "not_found"

    def rds_instance_state(self, arguments, named):
        identifier = arguments[0]
        try:
            response = self.client("rds").describe_db_instances(DBInstanceIdentifier=identifier)
        except Exception as exc:
            response = getattr(exc, "response", {})
            if response.get("Error", {}).get("Code") == "DBInstanceNotFound": return "not_found"
            raise
        instances = response.get("DBInstances", [])
        return instances[0].get("DBInstanceStatus", "unknown") if instances else "not_found"

    def cloudwatch_logs_decode(self, arguments, named):
        compressed = base64.b64decode(arguments[0], validate=True)
        return json.loads(gzip.decompress(compressed))

    def windows_event_parse(self, arguments, named):
        message = arguments[0]
        try:
            root = ElementTree.fromstring(message)
        except ElementTree.ParseError:
            return {"source": "", "event_id": "", "level": "", "message": message}
        system = root.find("{*}System")
        rendering = root.find("{*}RenderingInfo")
        provider = system.find("{*}Provider") if system is not None else None
        level_code = system.findtext("{*}Level", "") if system is not None else ""
        levels = {"1": "CRITICAL", "2": "ERROR", "3": "WARNING", "4": "INFORMATION", "5": "VERBOSE"}
        rendered = rendering.findtext("{*}Message", "") if rendering is not None else ""
        return {
            "source": provider.attrib.get("Name", "") if provider is not None else "",
            "event_id": system.findtext("{*}EventID", "") if system is not None else "",
            "level": levels.get(level_code, level_code),
            "message": rendered or message,
        }

    def cloudformation_respond(self, arguments, named):
        event, context, status = arguments[:3]
        reason = arguments[3] if len(arguments) == 4 else None
        body = json.dumps({
            "Status": status,
            "Reason": reason or f"See CloudWatch Logs: {context.get('log_stream_name', '-')}",
            "PhysicalResourceId": event.get("PhysicalResourceId", "separan-resource"),
            "StackId": event["StackId"], "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"], "NoEcho": False,
            "Data": {},
        }).encode("utf-8")
        request = urllib.request.Request(
            event["ResponseURL"], data=body, method="PUT",
            headers={"content-length": str(len(body)), "content-type": ""},
        )
        self.urlopen(request, timeout=10).read()
        return None


def create_aws_host_functions(**options):
    return AwsLambdaAdapter(**options).functions()
