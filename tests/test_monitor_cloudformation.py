import unittest
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "examples" / "monitor" / "monitor.yaml"


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


if __name__ == "__main__":
    unittest.main()
