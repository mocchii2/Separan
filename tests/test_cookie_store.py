import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class CookieStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / "tests" / "fixtures" / "io_runtime"
        self.capability = RuntimeCapabilities.local(self.directory)
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            if path.exists(): path.unlink()

    def test_external_key_round_trip_and_binary_container(self):
        self.paths.append(self.directory / "external.sepc")
        key = "0123456789abcdef0123456789abcdef"
        source = f'''function:main
jar = cookie_jar()
cookie_set(jar, "session", "abc", domain = "example.test", secure = true)
cookie_save_secure(jar, "external.sepc", key = "{key}")
loaded = cookie_load_secure("external.sepc", key = "{key}")
print cookie_get(loaded, "session")
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability)[1], "[REDACTED]\n")
        data = self.paths[0].read_bytes(); self.assertTrue(data.startswith(b"SEPARAN-COOKIE-STORE\0\x01\x03")); self.assertNotIn(b"abc", data)

    def test_password_argon2id_round_trip(self):
        self.paths.append(self.directory / "password.sepc")
        source = '''function:main
jar = cookie_jar()
cookie_set(jar, "portable", "value")
cookie_save_secure(jar, "password.sepc", password = "correct horse battery staple")
loaded = cookie_load_secure("password.sepc", password = "correct horse battery staple")
print cookie_get(loaded, "portable")
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability)[1], "[REDACTED]\n")

    def test_os_bound_provider_round_trip(self):
        self.paths.append(self.directory / "os.sepc"); keys = {}
        def provider(name, create):
            if create and name not in keys: keys[name] = b"K" * 32
            return keys.get(name)
        source = '''function:main
jar = cookie_jar()
cookie_set(jar, "session", "os-bound")
cookie_save_secure(jar, "os.sepc")
loaded = cookie_load_secure("os.sepc")
print cookie_get(loaded, "session")
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability, cookie_key_provider=provider)[1], "[REDACTED]\n")

    def test_tamper_wrong_key_mode_and_path_escape_fail(self):
        path = self.directory / "tamper.sepc"; self.paths.append(path); key = "0123456789abcdef0123456789abcdef"
        execute(f'function:main\njar = cookie_jar()\ncookie_set(jar, "x", "y")\ncookie_save_secure(jar, "tamper.sepc", key = "{key}")\nend_function:main\n', capabilities=self.capability)
        data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
        with self.assertRaises(SeparanError) as caught: execute(f'print cookie_load_secure("tamper.sepc", key = "{key}")\n', capabilities=self.capability)
        self.assertEqual(caught.exception.code, "E885")
        with self.assertRaises(SeparanError) as caught: execute('print cookie_load_secure("tamper.sepc", password = "x")\n', capabilities=self.capability)
        self.assertEqual(caught.exception.code, "E882")
        with self.assertRaises(SeparanError) as caught: execute(f'function:main\njar = cookie_jar()\ncookie_save_secure(jar, "../escape", key = "{key}")\nend_function:main\n', capabilities=self.capability)
        self.assertEqual(caught.exception.code, "E721")


if __name__ == "__main__": unittest.main()
