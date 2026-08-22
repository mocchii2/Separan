import base64
import hashlib
import io
import unittest
import zipfile
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "examples" / "monitor" / "cloudformation" / "monitor.yaml"
SOURCE_PATH = ROOT / "examples" / "monitor" / "lambda" / "monitor.sep"


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


class SeparanMonitorTemplateTests(unittest.TestCase):
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
                self.assertEqual("MonitorConfigBucket", properties["Code"]["S3Bucket"])
                self.assertEqual("runtime/separan-monitor.zip", properties["Code"]["S3Key"])
                self.assertEqual(handler, properties["Environment"]["Variables"]["SEPARAN_HANDLER"])
                self.assertNotIn("ZipFile", properties["Code"])

    def test_runtime_artifact_is_embedded_and_installed_before_functions(self):
        self.assertNotIn("SeparanRuntimeBucket", self.template["Parameters"])
        installer = self.resources["RuntimeInstallerFunction"]["Properties"]["Code"]["ZipFile"]
        self.assertIn("ARCHIVE = base64.b64decode", installer)
        self.assertIn("runtime/separan-monitor.zip", installer)
        encoded = installer.split('ARCHIVE = base64.b64decode("""', 1)[1].split('""")', 1)[0]
        archive = base64.b64decode(encoded)
        expected = installer.split('EXPECTED_SHA256 = "', 1)[1].split('"', 1)[0]
        self.assertEqual(expected, hashlib.sha256(archive).hexdigest())
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            self.assertIn("application.sep", package.namelist())
            self.assertIn("separan/lambda_runtime.py", package.namelist())
        self.assertLess(TEMPLATE_PATH.stat().st_size, 1_000_000)
        for name in ("NotifyFunction", "Log2Function", "StatusFunction", "ConfigBootstrapFunction"):
            self.assertEqual("RuntimeArtifact", self.resources[name]["DependsOn"])

    def test_monitor_business_logic_is_separan_source(self):
        application = SOURCE_PATH.read_text(encoding="utf-8")
        for handler in ("notify_handler", "log2_handler", "status_handler", "config_handler"):
            self.assertIn(f"function:{handler}(event, context)", application)
        self.assertNotIn("import boto3", application)
        self.assertEqual(1, self.source.count("ZipFile: |"))


if __name__ == "__main__":
    unittest.main()
