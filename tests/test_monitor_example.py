import base64
import gzip
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.lambda_aws import AwsLambdaAdapter
from separan.lambda_runtime import LambdaApplication, value_from_host
from separan.structural import inspect_source


class MonitorExampleTests(unittest.TestCase):
    @staticmethod
    def source_path():
        return ROOT / "examples" / "monitor" / "lambda" / "monitor.sep"

    def test_lambda_monitor_business_logic_is_separan_source(self):
        class SNS:
            def __init__(self): self.messages = []
            def publish(self, **kwargs): self.messages.append(kwargs); return {"MessageId": str(len(self.messages))}

        sns = SNS()
        environment = {
            "INGRESS_TOPIC": "topic", "EC2_IDS": "i-0123456789abcdef0",
            "EC2_NAMES": "WEB01", "RDS_IDS": "", "RDS_NAMES": "",
        }
        adapter = AwsLambdaAdapter(client_factory=lambda name: sns, environment=environment)
        source_path = self.source_path()
        application = LambdaApplication(
            source_path.read_text(encoding="utf-8"), str(source_path),
            "log2_handler", adapter.functions(),
        )
        xml = '<Event><System><Provider Name="Application Error"/><EventID>1000</EventID><Level>2</Level></System><RenderingInfo><Message>CRITICAL failure</Message></RenderingInfo></Event>'
        payload = {
            "logGroup": "/separan-monitor/windows/application",
            "logStream": "i-0123456789abcdef0",
            "logEvents": [{"message": xml}],
        }
        event = {"awslogs": {"data": base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()}}
        self.assertEqual({"ok": True}, application.handle(event))
        messages = [json.loads(item["Message"]) for item in sns.messages]
        self.assertEqual(["B", "C"], [item["notification_type"] for item in messages])
        self.assertEqual("Application Error", messages[1]["windows_source"])
        self.assertEqual("1000", messages[1]["event_id"])

    def test_lambda_monitor_exposes_all_four_separan_handlers(self):
        source_path = self.source_path()
        adapter = AwsLambdaAdapter(client_factory=lambda name: object(), environment={})
        application = LambdaApplication(
            source_path.read_text(encoding="utf-8"), str(source_path),
            "notify_handler", adapter.functions(),
        )
        self.assertTrue({"notify_handler", "log2_handler", "status_handler", "config_handler"} <= set(application.runtime.functions))

    def test_history_payload_is_utf8_bounded_and_marks_truncation(self):
        class DynamoDB:
            def __init__(self): self.item = None
            def put_item(self, **kwargs): self.item = kwargs["Item"]; return {}

        dynamodb = DynamoDB()
        adapter = AwsLambdaAdapter(
            client_factory=lambda name: dynamodb,
            environment={"TABLE_NAME": "history", "HISTORY_DAYS": "30"},
        )
        source_path = self.source_path()
        application = LambdaApplication(
            source_path.read_text(encoding="utf-8"), str(source_path),
            "notify_handler", adapter.functions(),
        )
        candidate = {
            "notification_type": "B",
            "resource_id": "i-0123456789abcdef0",
            "message": "界" * 30_000,
        }
        application.runtime.invoke(
            "store_history",
            [value_from_host(candidate), 1_700_000_000, "SENT", "NONE"],
        )
        payload = dynamodb.item["payload"]["S"]
        self.assertLessEqual(len(payload.encode("utf-8")), 60_000)
        self.assertTrue(dynamodb.item["payload_truncated"]["BOOL"])
        self.assertTrue(payload.endswith("界"))

    def test_dedup_identity_uses_stable_fields_and_normalized_message(self):
        adapter = AwsLambdaAdapter(client_factory=lambda name: object(), environment={})
        source_path = self.source_path()
        application = LambdaApplication(
            source_path.read_text(encoding="utf-8"), str(source_path),
            "notify_handler", adapter.functions(),
        )
        first = {
            "notification_type": "B", "resource_type": "EC2", "resource_id": "i-1",
            "state": "ALARM", "rule_id": "windows-error", "windows_source": "Application",
            "event_id": "1000", "title": "Windows log keyword",
            "message": " ERROR at 2026-08-22T10:00:00Z   disk full ",
        }
        second = dict(first, message="error at 2026-08-22T10:30:45Z disk full")
        different = dict(first, message="error: database unavailable")
        identity = lambda value: application.runtime.invoke("dedup_identity", [value_from_host(value)])
        self.assertEqual(identity(first), identity(second))
        self.assertNotEqual(identity(first), identity(different))

        metric_a = dict(first, notification_type="A", title="WEB01 CPU", message="value 91.2")
        metric_b = dict(metric_a, message="value 97.8 at another time")
        self.assertEqual(identity(metric_a), identity(metric_b))

    def test_monitor_uses_english_hierarchical_function_tags(self):
        source = self.source_path().read_text(encoding="utf-8")
        snapshot = inspect_source(source, str(self.source_path()))
        functions = {item.label: item for item in snapshot.blocks if item.kind == "function"}
        self.assertIn("monitor:notification:decision", functions["process_notification"].tags)
        self.assertIn("monitor:log:windows", functions["process_windows_log"].tags)
        self.assertIn("aws:dynamodb", functions["store_history"].tags)
        self.assertNotIn("重大", source)


if __name__ == "__main__":
    unittest.main()
