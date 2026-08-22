import base64
import gzip
import json
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "examples" / "monitor" / "monitor-inline-python.yaml"
NATIVE_TEMPLATE_PATH = ROOT / "examples" / "monitor" / "monitor.yaml"
NATIVE_SOURCE_PATH = ROOT / "examples" / "monitor" / "lambda" / "monitor.sep"


class CloudFormationLoader(yaml.SafeLoader):
    """Load CloudFormation YAML while retaining intrinsic-tag payloads."""


def construct_intrinsic(loader, tag_suffix, node):
    if isinstance(node, ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, MappingNode):
        return loader.construct_mapping(node)
    raise TypeError(f"Unsupported YAML node for !{tag_suffix}: {type(node).__name__}")


CloudFormationLoader.add_multi_constructor("!", construct_intrinsic)


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeDynamoDB:
    def __init__(self):
        self.items = {}

    @staticmethod
    def _key(value):
        return value["pk"]["S"], value["sk"]["S"]

    def get_item(self, **kwargs):
        item = self.items.get(self._key(kwargs["Key"]))
        return {"Item": item} if item is not None else {}

    def put_item(self, **kwargs):
        item = kwargs["Item"]
        key = self._key(item)
        if "ConditionExpression" in kwargs and key in self.items:
            now = int(kwargs["ExpressionAttributeValues"][":now"]["N"])
            if int(self.items[key]["expires_at"]["N"]) >= now:
                raise FakeClientError("ConditionalCheckFailedException")
        self.items[key] = item

    def delete_item(self, **kwargs):
        self.items.pop(self._key(kwargs["Key"]), None)


class FakeS3:
    class Body:
        def __init__(self, value):
            self.value = value

        def read(self):
            return self.value

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        value = {"rules": []} if key.endswith("suppression.json") else {"weekly": [], "dates": []}
        return {"Body": self.Body(json.dumps(value).encode("utf-8"))}


class FakeSNS:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def publish(self, **kwargs):
        if self.fail:
            raise RuntimeError("simulated SNS failure")
        self.messages.append(kwargs)
        return {"MessageId": str(len(self.messages))}


def execute_inline_lambda(code, clients, environment):
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda name: clients[name]
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = FakeClientError
    botocore.exceptions = exceptions
    modules = {"boto3": boto3, "botocore": botocore, "botocore.exceptions": exceptions}
    namespace = {}
    with patch.dict(sys.modules, modules), patch.dict(os.environ, environment, clear=False):
        exec(code, namespace)
    namespace["os"] = types.SimpleNamespace(environ={**os.environ, **environment})
    return namespace


class MonitorCloudFormationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.template = yaml.load(cls.source, Loader=CloudFormationLoader)
        cls.resources = cls.template["Resources"]

    def test_template_is_single_deployable_document(self):
        self.assertEqual("2010-09-09", self.template["AWSTemplateFormatVersion"])
        self.assertIn("AWS::CloudFormation::Interface", self.template["Metadata"])
        self.assertIn("Outputs", self.template)
        self.assertNotRegex(self.source, r"(?m)^\s*<<:\s*\*")

    def test_supports_exactly_five_ec2_and_five_rds_slots(self):
        parameters = self.template["Parameters"]
        self.assertEqual(5, sum(f"Ec2Instance{i}" in parameters for i in range(1, 6)))
        self.assertEqual(5, sum(f"RdsInstance{i}" in parameters for i in range(1, 6)))
        self.assertNotIn("Ec2Instance6", parameters)
        self.assertNotIn("RdsInstance6", parameters)

    def test_optional_teams_ids_are_format_checked(self):
        parameters = self.template["Parameters"]
        for name in ("TeamsTenantId", "TeamsTeamId", "TeamsChannelId"):
            with self.subTest(parameter=name):
                self.assertIn("AllowedPattern", parameters[name])

    def test_inline_lambda_programs_compile(self):
        for name in ("NotifyFunction", "Log2Function", "StatusFunction", "ConfigBootstrapFunction"):
            with self.subTest(function=name):
                code = self.resources[name]["Properties"]["Code"]["ZipFile"]
                compile(code, f"monitor.yaml::{name}", "exec")

    def test_requested_notification_pipeline_is_present(self):
        expected_types = {
            "NotifyFunction": "AWS::Lambda::Function",
            "Log2Function": "AWS::Lambda::Function",
            "StatusFunction": "AWS::Lambda::Function",
            "NotifyIngressTopic": "AWS::SNS::Topic",
            "NotifyIngressTopicPolicy": "AWS::SNS::TopicPolicy",
            "MonitorTable": "AWS::DynamoDB::Table",
            "MonitorConfigBucket": "AWS::S3::Bucket",
            "StatusScheduleRule": "AWS::Events::Rule",
            "Ec2StateRule": "AWS::Events::Rule",
            "RdsEventRule": "AWS::Events::Rule",
        }
        for name, resource_type in expected_types.items():
            with self.subTest(resource=name):
                self.assertEqual(resource_type, self.resources[name]["Type"])

    def test_metric_alarms_cover_all_targets(self):
        alarms = {
            name
            for name, resource in self.resources.items()
            if resource.get("Type") == "AWS::CloudWatch::Alarm"
        }
        expected = {
            f"{prefix}{index}"
            for prefix in ("Ec2CpuAlarm", "Ec2DiskAlarm", "RdsCpuAlarm", "RdsStorageAlarm")
            for index in range(1, 6)
        }
        self.assertEqual(expected, alarms)

    def test_all_notification_types_and_destinations_have_templates(self):
        code = self.resources["NotifyFunction"]["Properties"]["Code"]["ZipFile"]
        for notification_type in ("A", "A2", "B", "C", "D", "E", "F"):
            self.assertIn(f'"{notification_type}":{{"email":', code)
        for channel in ("email", "sms", "teams"):
            self.assertIn(f'"{channel}":', code)

    def test_retention_suppression_and_bootstrap_configuration_are_present(self):
        table = self.resources["MonitorTable"]["Properties"]
        self.assertEqual(
            {"AttributeName": "expires_at", "Enabled": True},
            table["TimeToLiveSpecification"],
        )
        notify_code = self.resources["NotifyFunction"]["Properties"]["Code"]["ZipFile"]
        self.assertIn("DUPLICATE_WITHIN_WINDOW", notify_code)
        self.assertIn("STATE_TRANSITION_GRACE", notify_code)
        self.assertIn("USER_SUPPRESSION_RULE", notify_code)
        bootstrap_code = self.resources["ConfigBootstrapFunction"]["Properties"]["Code"]["ZipFile"]
        self.assertIn("config/suppression.json", bootstrap_code)
        self.assertIn("config/holidays.json", bootstrap_code)

    def test_unchanged_state_does_not_extend_metric_suppression(self):
        ddb, sns = FakeDynamoDB(), FakeSNS()
        state_key = ("STATE#EC2#i-0123456789abcdef0", "CURRENT")
        ddb.items[state_key] = {
            "pk": {"S": state_key[0]},
            "sk": {"S": state_key[1]},
            "state": {"S": "running"},
            "previous_state": {"S": "pending"},
            "changed_at": {"N": "700"},
            "suppress_metrics_until": {"N": "1000"},
            "expires_at": {"N": "999999"},
        }
        code = self.resources["StatusFunction"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"dynamodb": ddb, "ec2": object(), "rds": object(), "sns": sns},
            {
                "TABLE_NAME": "table",
                "INGRESS_TOPIC": "topic",
                "HISTORY_DAYS": "30",
                "STARTUP_SUPPRESSION": "15",
                "SHUTDOWN_SUPPRESSION": "5",
                "REBOOT_SUPPRESSION": "15",
                "EC2_IDS": "i-0123456789abcdef0",
                "EC2_NAMES": "WEB01",
                "RDS_IDS": "",
                "RDS_NAMES": "",
            },
        )
        with patch("time.time", return_value=900):
            namespace["transition"](
                "EC2", "i-0123456789abcdef0", "WEB01", "running", "test", "unchanged"
            )
        self.assertEqual("1000", ddb.items[state_key]["suppress_metrics_until"]["N"])
        self.assertEqual("700", ddb.items[state_key]["changed_at"]["N"])
        self.assertEqual([], sns.messages)

    def test_state_change_starts_a_finite_metric_grace_period(self):
        ddb, sns = FakeDynamoDB(), FakeSNS()
        state_key = ("STATE#RDS#database-1", "CURRENT")
        ddb.items[state_key] = {
            "pk": {"S": state_key[0]},
            "sk": {"S": state_key[1]},
            "state": {"S": "stopped"},
            "changed_at": {"N": "100"},
            "suppress_metrics_until": {"N": "0"},
            "expires_at": {"N": "999999"},
        }
        code = self.resources["StatusFunction"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"dynamodb": ddb, "ec2": object(), "rds": object(), "sns": sns},
            {
                "TABLE_NAME": "table",
                "INGRESS_TOPIC": "topic",
                "HISTORY_DAYS": "30",
                "STARTUP_SUPPRESSION": "15",
                "SHUTDOWN_SUPPRESSION": "5",
                "REBOOT_SUPPRESSION": "15",
                "EC2_IDS": "",
                "EC2_NAMES": "",
                "RDS_IDS": "database-1",
                "RDS_NAMES": "DB01",
            },
        )
        with patch("time.time", return_value=300):
            namespace["transition"]("RDS", "database-1", "DB01", "available", "test", "started")
        self.assertEqual("1200", ddb.items[state_key]["suppress_metrics_until"]["N"])
        self.assertEqual(1, len(sns.messages))

    def test_first_ec2_push_is_not_lost_before_periodic_baseline(self):
        ddb, sns = FakeDynamoDB(), FakeSNS()
        code = self.resources["StatusFunction"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"dynamodb": ddb, "ec2": object(), "rds": object(), "sns": sns},
            {
                "TABLE_NAME": "table",
                "INGRESS_TOPIC": "topic",
                "HISTORY_DAYS": "30",
                "STARTUP_SUPPRESSION": "15",
                "SHUTDOWN_SUPPRESSION": "5",
                "REBOOT_SUPPRESSION": "15",
                "EC2_IDS": "i-0123456789abcdef0",
                "EC2_NAMES": "WEB01",
                "RDS_IDS": "",
                "RDS_NAMES": "",
            },
        )
        with patch("time.time", return_value=300):
            namespace["handler"](
                {
                    "source": "aws.ec2",
                    "detail-type": "EC2 Instance State-change Notification",
                    "detail": {"instance-id": "i-0123456789abcdef0", "state": "stopping"},
                },
                None,
            )
        self.assertEqual(1, len(sns.messages))
        message = json.loads(sns.messages[0]["Message"])
        self.assertEqual("stopping", message["state"])
        state = ddb.items[("STATE#EC2#i-0123456789abcdef0", "CURRENT")]
        self.assertEqual("600", state["suppress_metrics_until"]["N"])

    def test_periodic_api_failure_notifies_without_corrupting_known_state(self):
        class DeniedEC2:
            def describe_instances(self, **kwargs):
                raise FakeClientError("UnauthorizedOperation")

        ddb, sns = FakeDynamoDB(), FakeSNS()
        state_key = ("STATE#EC2#i-0123456789abcdef0", "CURRENT")
        original = {
            "pk": {"S": state_key[0]},
            "sk": {"S": state_key[1]},
            "state": {"S": "running"},
            "changed_at": {"N": "100"},
            "suppress_metrics_until": {"N": "200"},
            "expires_at": {"N": "999999"},
        }
        ddb.items[state_key] = original.copy()
        code = self.resources["StatusFunction"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"dynamodb": ddb, "ec2": DeniedEC2(), "rds": object(), "sns": sns},
            {
                "TABLE_NAME": "table",
                "INGRESS_TOPIC": "topic",
                "HISTORY_DAYS": "30",
                "STARTUP_SUPPRESSION": "15",
                "SHUTDOWN_SUPPRESSION": "5",
                "REBOOT_SUPPRESSION": "15",
                "EC2_IDS": "i-0123456789abcdef0",
                "EC2_NAMES": "WEB01",
                "RDS_IDS": "",
                "RDS_NAMES": "",
            },
        )
        namespace["scheduled"]()
        self.assertEqual("running", ddb.items[state_key]["state"]["S"])
        message = json.loads(sns.messages[0]["Message"])
        self.assertEqual("check_failed", message["state"])
        self.assertIn("UnauthorizedOperation", message["message"])

    def test_weekly_and_date_breaks_continue_after_midnight(self):
        code = self.resources["NotifyFunction"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"dynamodb": FakeDynamoDB(), "s3": FakeS3(), "sns": FakeSNS()},
            {
                "TABLE_NAME": "table",
                "CONFIG_BUCKET": "bucket",
                "EMAIL_TOPIC": "email",
                "SMS_TOPIC": "sms",
                "TEAMS_TOPIC": "teams",
                "EMAIL_ENABLED": "false",
                "SMS_ENABLED": "false",
                "TEAMS_ENABLED": "false",
                "ROUTES_JSON": "{}",
                "HISTORY_DAYS": "30",
                "DEDUP_MINUTES": "30",
                "DEFAULT_TIMEZONE": "UTC",
            },
        )
        tuesday_0200 = int(datetime(2026, 8, 18, 2, tzinfo=timezone.utc).timestamp())
        friday_0200 = int(datetime(2027, 1, 1, 2, tzinfo=timezone.utc).timestamp())
        weekly = {
            "timezone": "UTC",
            "weekly": [{"enabled": True, "days": ["MON"], "start": "22:00", "end": "06:00"}],
            "dates": [],
        }
        dated = {
            "timezone": "UTC",
            "weekly": [],
            "dates": [{"enabled": True, "date": "2026-12-31", "start": "22:00", "end": "06:00"}],
        }
        self.assertEqual("HOLIDAY_WEEKLY", namespace["holiday"](weekly, tuesday_0200))
        self.assertEqual("HOLIDAY_DATE", namespace["holiday"](dated, friday_0200))

    def test_failed_delivery_releases_dedup_reservation_and_records_failure(self):
        ddb = FakeDynamoDB()
        code = self.resources["NotifyFunction"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"dynamodb": ddb, "s3": FakeS3(), "sns": FakeSNS(fail=True)},
            {
                "TABLE_NAME": "table",
                "CONFIG_BUCKET": "bucket",
                "SUPPRESSION_KEY": "config/suppression.json",
                "HOLIDAY_KEY": "config/holidays.json",
                "EMAIL_TOPIC": "email",
                "SMS_TOPIC": "sms",
                "TEAMS_TOPIC": "teams",
                "EMAIL_ENABLED": "true",
                "SMS_ENABLED": "false",
                "TEAMS_ENABLED": "false",
                "ROUTES_JSON": '{"A":"email"}',
                "HISTORY_DAYS": "30",
                "DEDUP_MINUTES": "30",
                "DEFAULT_TIMEZONE": "UTC",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "SNS failure"), patch("time.time", return_value=1000):
            namespace["process"](
                {
                    "notification_type": "A",
                    "resource_type": "EC2",
                    "resource_id": "i-0123456789abcdef0",
                    "resource_name": "WEB01",
                    "state": "ALARM",
                    "message": "CPU high",
                }
            )
        self.assertFalse(any(key[0].startswith("DEDUP#") for key in ddb.items))
        histories = [item for key, item in ddb.items.items() if key[0].startswith("HISTORY#")]
        self.assertEqual("DELIVERY_FAILED", histories[0]["status"]["S"])

    def test_windows_xml_event_produces_keyword_and_event_notifications(self):
        sns = FakeSNS()
        code = self.resources["Log2Function"]["Properties"]["Code"]["ZipFile"]
        namespace = execute_inline_lambda(
            code,
            {"sns": sns},
            {
                "INGRESS_TOPIC": "topic",
                "KEYWORDS": "ERROR,CRITICAL,重大",
                "EC2_IDS": "i-0123456789abcdef0",
                "EC2_NAMES": "WEB01",
                "RDS_IDS": "",
                "RDS_NAMES": "",
            },
        )
        xml = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><Provider Name="Application Error"/><EventID>1000</EventID><Level>2</Level></System><RenderingInfo><Message>ERROR process stopped</Message></RenderingInfo></Event>"""
        payload = {
            "logGroup": "/separan-monitor/windows/application",
            "logStream": "i-0123456789abcdef0",
            "logEvents": [{"message": xml}],
        }
        event = {
            "awslogs": {
                "data": base64.b64encode(gzip.compress(json.dumps(payload).encode("utf-8"))).decode("ascii")
            }
        }
        namespace["handler"](event, None)
        messages = [json.loads(item["Message"]) for item in sns.messages]
        self.assertEqual(["B", "C"], [item["notification_type"] for item in messages])
        self.assertEqual("Application Error", messages[1]["windows_source"])
        self.assertEqual("1000", messages[1]["event_id"])
        self.assertEqual("ERROR", messages[1]["event_level"])

    def test_cloudwatch_agent_uses_xml_instance_stream_and_valid_ssm_arn(self):
        config = self.resources["CloudWatchAgentConfig"]["Properties"]["Value"]
        self.assertEqual(3, config.count('"event_format":"xml"'))
        self.assertEqual(3, config.count('"log_stream_name":"{instance_id}"'))
        policy = self.resources["Ec2AgentManagedPolicy"]["Properties"]["PolicyDocument"]
        ssm_statement = next(
            statement for statement in policy["Statement"] if statement["Action"] == "ssm:GetParameter"
        )
        self.assertIn(":parameter/", ssm_statement["Resource"])
        for prefix in ("InstallAgent", "ConfigureAgent"):
            for index in range(1, 6):
                association = self.resources[f"{prefix}{index}"]
                self.assertEqual(900, association["Properties"]["WaitForSuccessTimeoutSeconds"])


class NativeSeparanMonitorTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = NATIVE_TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.template = yaml.load(cls.source, Loader=CloudFormationLoader)
        cls.resources = cls.template["Resources"]

    def test_all_lambda_functions_use_one_packaged_separan_application(self):
        handlers = {
            "NotifyFunction": "notify_handler",
            "Log2Function": "log2_handler",
            "StatusFunction": "status_handler",
            "ConfigBootstrapFunction": "config_handler",
        }
        for name, handler in handlers.items():
            with self.subTest(function=name):
                properties = self.resources[name]["Properties"]
                self.assertEqual("python3.13", properties["Runtime"])
                self.assertEqual("index.handler", properties["Handler"])
                self.assertEqual("SeparanRuntimeBucket", properties["Code"]["S3Bucket"])
                self.assertEqual("SeparanRuntimeKey", properties["Code"]["S3Key"])
                self.assertEqual(handler, properties["Environment"]["Variables"]["SEPARAN_HANDLER"])
                self.assertNotIn("ZipFile", properties["Code"])

    def test_runtime_artifact_parameters_are_visible_in_cloudformation_gui(self):
        parameters = self.template["Parameters"]
        self.assertIn("SeparanRuntimeBucket", parameters)
        self.assertIn("SeparanRuntimeKey", parameters)
        groups = self.template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterGroups"]
        self.assertTrue(any("SeparanRuntimeBucket" in group["Parameters"] for group in groups))

    def test_monitor_business_logic_is_not_inline_python(self):
        application = NATIVE_SOURCE_PATH.read_text(encoding="utf-8")
        for handler in ("notify_handler", "log2_handler", "status_handler", "config_handler"):
            self.assertIn(f"function:{handler}(event, context)", application)
        self.assertNotIn("import boto3", self.source)
        self.assertNotIn("ZipFile: |", self.source)


if __name__ == "__main__":
    unittest.main()
