import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C_ROOT = ROOT / "reference" / "c"


class GatewayWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            raise unittest.SkipTest("a C compiler is required for gateway tests")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary.name) / ("separan-gw.exe" if __import__("os").name == "nt" else "separan-gw")
        sources = [
            C_ROOT / "src" / "separan_gw.c",
            C_ROOT / "src" / "separan_core.c",
            C_ROOT / "src" / "separan_lexer.c",
            C_ROOT / "src" / "separan_files.c",
            C_ROOT / "src" / "separan_runtime.c",
        ]
        subprocess.run([
            compiler, "-O1", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I", str(C_ROOT / "include"), "-o", str(cls.binary),
            *(str(source) for source in sources), "-lm",
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_config_drives_stdio_http_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, body = "ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            config = root / "separan-gw.conf"
            config.write_text(f"# gateway app\nsource = {app}\ntransport = stdio\n", encoding="utf-8")
            request = json.dumps({"method": "GET", "path": "/health"}) + "\n"
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                input=request, text=True, capture_output=True, check=True,
            )
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], 200)
            self.assertEqual(response["body"], "ok")

    def test_unknown_supervisor_setting_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "separan-gw.conf"
            config.write_text("workers = 4\n", encoding="utf-8")
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported setting 'workers'", result.stderr)

    def test_only_stdio_transport_is_accepted_for_now(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "separan-gw.conf"
            config.write_text("transport = fastcgi\n", encoding="utf-8")
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("only stdio", result.stderr)

    def test_help_documents_config(self):
        result = subprocess.run([str(self.binary), "--help"], text=True, capture_output=True, check=True)
        self.assertIn("--config <separan-gw.conf>", result.stdout)


if __name__ == "__main__":
    unittest.main()
