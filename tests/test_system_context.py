import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class SystemContextTests(unittest.TestCase):
    def test_stable_read_only_execution_context(self):
        script = ROOT / "examples" / "context.sep"
        source = '''SEP:main
print type_of(system)
print system.version
print system.engine
print system.script_name
print system.script_path
print system.script_dir
print system.arg_count
print system.args
print system.runtime
print system.cpu_count > 0
print system.pid > 0
print is_empty(system.hostname)
print system
END_SEP:main
'''
        output = execute(source, script_path=str(script), command_arguments=["server1", "--debug"])[1].splitlines()
        self.assertEqual(output[:4], ["system", "0.2.0-alpha.13", "python-reference", "context.sep"])
        self.assertEqual(Path(output[4]), script.resolve())
        self.assertEqual(Path(output[5]), script.resolve().parent)
        self.assertEqual(output[6:], ["2", "[server1, --debug]", "python", "true", "true", "false", "system:[READONLY]"])

    def test_os_and_arch_are_normalized(self):
        output = execute('print system.os\nprint system.arch\n')[1].splitlines()
        self.assertIn(output[0], ("windows", "linux", "macos", "unknown"))
        self.assertNotEqual(output[1], "")

    def test_pathless_source_uses_typed_empty_context_values(self):
        source = '''print system.script_path is EMPTY
print system.script_name is EMPTY
print system.script_dir is EMPTY
'''
        self.assertEqual(execute(source)[1], "true\ntrue\ntrue\n")

    def test_system_cannot_be_shadowed_or_assigned(self):
        cases = (
            ("system = 1\n", "E215"),
            ("const system = 1\n", "E215"),
            ("SEP:system\nEND_SEP:system\n", "E215"),
            ("SEP:test(system)\nEND_SEP:test\n", "E215"),
            ("SEP:main\nsystem.os = \"linux\"\nEND_SEP:main\n", "E214"),
        )
        for source, code in cases:
            with self.subTest(source=source):
                with self.assertRaises(SeparanError) as caught: execute(source)
                self.assertEqual(caught.exception.code, code)


if __name__ == "__main__": unittest.main()
