import sys
import unittest
import shutil
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class IoJsonCapabilityTests(unittest.TestCase):
    def test_text_and_bytes_round_trip(self):
        directory = ROOT / "tests" / "fixtures" / "io_runtime"
        directory.mkdir(exist_ok=True)
        capability = RuntimeCapabilities.local(directory)
        source = '''function:main
write_text("note.txt", "日本語")
append_text("note.txt", "!")
print read_text("note.txt")
data = secure_random_bytes(8)
write_bytes("data.bin", data)
print length(read_bytes("data.bin"))
end_function:main
'''
        try: self.assertEqual(execute(source, capabilities=capability)[1], "日本語!\n8\n")
        finally:
            for name in ("note.txt", "data.bin"):
                path = directory / name
                if path.exists(): path.unlink()

    def test_capability_denial_is_catchable(self):
        capability = RuntimeCapabilities.none(ROOT)
        source = '''function:main
try :read
print read_text("README.md")
catch permission_error :read
print "denied"
endtry:read
end_function:main
'''
        self.assertEqual(execute(source, capabilities=capability)[1], "denied\n")
        with self.assertRaises(SeparanError) as caught:
            execute('print glob("*.md")\n', capabilities=capability)
        self.assertEqual(caught.exception.code, "E720")

    def test_environment_allowlists(self):
        capability = RuntimeCapabilities(ROOT, readable_environment=frozenset({"SAFE"}), writable_environment=frozenset())
        self.assertEqual(execute('print env_get("SAFE")\n', environment_variables={"SAFE": "yes"}, capabilities=capability)[1], "yes\n")
        with self.assertRaises(SeparanError) as caught:
            execute('print env_get("SECRET")\n', environment_variables={"SECRET": "no"}, capabilities=capability)
        self.assertEqual(caught.exception.code, "E720")

    def test_json_is_deterministic_and_uses_objects(self):
        source = '''data = json_decode("{\\"z\\":1,\\"a\\":{\\"name\\":\\"Alice\\"}}")
print data.a.name
print json_encode(data)
'''
        self.assertEqual(execute(source)[1], 'Alice\n{"a":{"name":"Alice"},"z":1}\n')

    def test_json_rejects_duplicate_keys_and_heterogeneous_arrays(self):
        for text, code in (('{"a":1,"a":2}', "E740"), ('[1,"x"]', "E203")):
            with self.subTest(text=text):
                encoded = text.replace("\\", "\\\\").replace('"', '\\"')
                with self.assertRaises(SeparanError) as caught: execute(f'print json_decode("{encoded}")\n')
                self.assertEqual(caught.exception.code, code)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(SeparanError) as caught: execute('print read_text("../secret")\n')
        self.assertEqual(caught.exception.code, "E721")

    def test_standard_streams_are_injectable(self):
        errors = StringIO()
        source = 'function:main\nname = input("Name: ")\nprint name\nprint_error "warning"\nend_function:main\n'
        output = execute(source, input_stream=StringIO("Alice\n"), error_output=errors)[1]
        self.assertEqual(output, "Name: Alice\n"); self.assertEqual(errors.getvalue(), "warning\n")
        with self.assertRaises(SeparanError) as caught: execute('print input()\n', input_stream=StringIO(""))
        self.assertEqual(caught.exception.code, "E724")

    def test_high_level_file_and_directory_utilities(self):
        root = ROOT / "tests" / "fixtures" / "io_runtime"; work = root / "work"
        if work.exists(): shutil.rmtree(work)
        capability = RuntimeCapabilities.local(root)
        source = '''function:main
create_directory("work")
write_text("work/source.txt", "a\\nb\\n")
print file_exists("work/source.txt")
print directory_exists("work")
print file_size("work/source.txt")
print read_lines("work/source.txt")
copy_file("work/source.txt", "work/copy.txt")
move_file("work/copy.txt", "work/moved.txt")
print list_directory("work")
print file_name("work/source.txt")
print file_extension("work/source.txt")
print parent_directory("work/source.txt")
delete_file("work/source.txt")
delete_file("work/moved.txt")
delete_directory("work")
print directory_exists("work")
end_function:main
'''
        try:
            self.assertEqual(execute(source, capabilities=capability)[1], "true\ntrue\n4\n[a, b]\n[moved.txt, source.txt]\nsource.txt\ntxt\nwork\nfalse\n")
        finally:
            if work.exists(): shutil.rmtree(work)

    def test_file_utilities_reject_overwrite_and_capability_denial(self):
        root = ROOT / "tests" / "fixtures" / "io_runtime"; work = root / "work"
        if work.exists(): shutil.rmtree(work)
        work.mkdir(); (work / "a.txt").write_text("a", encoding="utf-8"); (work / "b.txt").write_text("b", encoding="utf-8")
        try:
            with self.assertRaises(SeparanError) as caught:
                execute('function:main\ncopy_file("work/a.txt", "work/b.txt")\nend_function:main\n', capabilities=RuntimeCapabilities.local(root))
            self.assertEqual(caught.exception.code, "E725")
            with self.assertRaises(SeparanError) as caught:
                execute('print file_exists("work/a.txt")\n', capabilities=RuntimeCapabilities.none(root))
            self.assertEqual(caught.exception.code, "E720")
        finally: shutil.rmtree(work)


if __name__ == "__main__": unittest.main()
