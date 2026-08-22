import base64
import gzip
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.errors import SeparanError
from separan.lambda_aws import AwsLambdaAdapter
from separan.lambda_build import build_lambda_package
from separan.lambda_runtime import HostFunction, LambdaApplication, value_from_host, value_to_host


class Context:
    aws_request_id = "request-123"
    function_name = "separan-test"
    log_stream_name = "stream"
    def get_remaining_time_in_millis(self): return 1234


class LambdaRuntimeTests(unittest.TestCase):
    def test_application_invokes_separan_handler_and_converts_values(self):
        source = '''function:handler(event, context)
object:result
message = event.message
request_id = context.aws_request_id
remaining = context.remaining_time_milliseconds
end_object:result
return result
end_function:handler
'''
        application = LambdaApplication(source)
        self.assertEqual(
            {"message": "hello", "request_id": "request-123", "remaining": 1234},
            application.handle({"message": "hello"}, Context()),
        )
        self.assertEqual("again", application.handle({"message": "again"}, Context())["message"])

    def test_host_function_is_explicit_and_cannot_replace_builtin(self):
        calls = []
        function = HostFunction("host_echo", 1, 1, lambda arguments, named: calls.append(arguments[0]) or arguments[0])
        source = '''function:handler(event, context)
return host_echo(event.value)
end_function:handler
'''
        self.assertEqual("ok", LambdaApplication(source, host_functions={"host_echo": function}).handle({"value": "ok"}))
        self.assertEqual(["ok"], calls)
        with self.assertRaises(ValueError):
            LambdaApplication(source, host_functions={"length": function})

    def test_host_failure_is_a_separan_diagnostic(self):
        function = HostFunction("fail_host", 0, 0, lambda arguments, named: (_ for _ in ()).throw(RuntimeError("boom")))
        source = '''function:handler(event, context)
return fail_host()
end_function:handler
'''
        with self.assertRaises(SeparanError) as caught:
            LambdaApplication(source, host_functions={"fail_host": function}).handle({})
        self.assertEqual("E980", caught.exception.code)
        self.assertIn("application.sep:2", str(caught.exception))

    def test_recursive_boundary_conversion(self):
        original = {"records": [{"ok": True, "count": 2}], "nothing": None}
        self.assertEqual(original, value_to_host(value_from_host(original)))

    def test_package_contains_source_entrypoint_and_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "app.sep"; output = root / "app.zip"
            source.write_text("function:handler(event, context)\nreturn null\nend_function:handler\n", encoding="utf-8")
            build_lambda_package(source, output, install_dependencies=False)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("application.sep", names)
                self.assertIn("index.py", names)
                self.assertIn("separan/lambda_runtime.py", names)
                self.assertEqual(b"from separan.lambda_entry import handler\n", archive.read("index.py"))


class FakeBody:
    def __init__(self, value): self.value = value
    def read(self): return self.value


class FakeS3:
    def get_object(self, **kwargs): return {"Body": FakeBody(b'{"enabled":true}')}


class FakeSNS:
    def __init__(self): self.requests = []
    def publish(self, **kwargs): self.requests.append(kwargs); return {"MessageId": "m-1"}


class AwsLambdaAdapterTests(unittest.TestCase):
    def test_cloudwatch_and_windows_transport_parsing(self):
        adapter = AwsLambdaAdapter(client_factory=lambda name: None)
        payload = {"logGroup": "/test", "logEvents": [{"message": "hello"}]}
        encoded = base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
        self.assertEqual(payload, adapter.cloudwatch_logs_decode([encoded], {}))
        event = '<Event><System><Provider Name="Application Error"/><EventID>1000</EventID><Level>2</Level></System><RenderingInfo><Message>重大 error</Message></RenderingInfo></Event>'
        parsed = adapter.windows_event_parse([event], {})
        self.assertEqual("Application Error", parsed["source"])
        self.assertEqual("1000", parsed["event_id"])
        self.assertEqual("ERROR", parsed["level"])

    def test_sns_and_s3_are_narrow_host_primitives(self):
        clients = {"sns": FakeSNS(), "s3": FakeS3()}
        adapter = AwsLambdaAdapter(client_factory=clients.get)
        self.assertEqual("m-1", adapter.sns_publish(["arn:topic", "body", "subject"], {}))
        self.assertEqual({"enabled": True}, adapter.s3_read_json(["bucket", "key"], {}))
        self.assertEqual("subject", clients["sns"].requests[0]["Subject"])


if __name__ == "__main__": unittest.main()
