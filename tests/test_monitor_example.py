import base64
import gzip
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.lambda_aws import AwsLambdaAdapter
from separan.lambda_runtime import LambdaApplication


class MonitorExampleTests(unittest.TestCase):
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
        source_path = ROOT / "examples" / "monitor" / "lambda" / "monitor.sep"
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
        source_path = ROOT / "examples" / "monitor" / "lambda" / "monitor.sep"
        adapter = AwsLambdaAdapter(client_factory=lambda name: object(), environment={})
        application = LambdaApplication(
            source_path.read_text(encoding="utf-8"), str(source_path),
            "notify_handler", adapter.functions(),
        )
        self.assertTrue({"notify_handler", "log2_handler", "status_handler", "config_handler"} <= set(application.runtime.functions))


if __name__ == "__main__":
    unittest.main()
