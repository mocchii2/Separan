import sys
import os
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class ProcessExecutionTests(unittest.TestCase):
    def setUp(self):
        self.executable = str(Path(sys.executable).resolve())
        self.command = self.executable.replace("\\", "\\\\")
        self.capability = replace(RuntimeCapabilities.local(ROOT), allowed_commands=frozenset({self.executable}))

    def test_exec_uses_direct_argv_and_returns_fixed_result(self):
        source = f'''function:main
result = exec("{self.command}", ["-c", "import sys;print(sys.argv[1])", "& del * | echo unsafe"])
print result.exit_code
print result.stdout
print result.stderr
print result.timed_out
print length(result.stdout_bytes)
end_function:main
'''
        output = execute(source, capabilities=self.capability)[1]
        process_line = "& del * | echo unsafe" + os.linesep
        self.assertEqual(output, f"0\n{process_line}\n\nfalse\n{len(process_line.encode())}\n")

    def test_nonzero_result_and_checked_error(self):
        source = f'''function:main
result = exec("{self.command}", ["-c", "raise SystemExit(7)"])
print result.exit_code
try :checked
exec_checked("{self.command}", ["-c", "raise SystemExit(4)"])
catch command_error :checked
print "failed"
endtry:checked
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability)[1], "7\nfailed\n")

    def test_timeout_and_output_limit(self):
        source = f'''function:main
result = exec("{self.command}", ["-c", "import time;time.sleep(1)"], timeout = duration("10ms"))
print result.timed_out
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability)[1], "true\n")
        with self.assertRaises(SeparanError) as caught:
            execute(f'print exec("{self.command}", ["-c", "print(12345)"], max_stdout_bytes = 2)\n', capabilities=self.capability)
        self.assertEqual(caught.exception.code, "E805")

        caught_source = f'''function:main
try :timeout
exec_checked("{self.command}", ["-c", "import time;time.sleep(1)"], timeout = duration("10ms"))
catch process_error :timeout
print "timed out"
endtry:timeout
end_function:main
'''
        self.assertEqual(execute(caught_source, capabilities=self.capability)[1], "timed out\n")

    def test_command_exists_and_capability_denial(self):
        self.assertEqual(execute(f'print command_exists("{self.command}")\n', capabilities=self.capability)[1], "true\n")
        denied = RuntimeCapabilities.none(ROOT)
        with self.assertRaises(SeparanError) as caught: execute(f'print exec("{self.command}", [])\n', capabilities=denied)
        self.assertEqual(caught.exception.code, "E720")

    def test_shell_requires_separate_capability(self):
        with self.assertRaises(SeparanError) as caught: execute('print shell_exec("echo unsafe")\n', capabilities=self.capability)
        self.assertEqual(caught.exception.code, "E720")


if __name__ == "__main__": unittest.main()
