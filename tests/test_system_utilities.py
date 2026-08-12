import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class SystemUtilityTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: execute(source, "utility.sep")
        self.assertEqual(caught.exception.code, code)

    def test_named_arguments_are_parsed_and_checked(self):
        self.assertEqual(execute('print regex_search("error", "ERROR", ignore_case = true)\n')[1], "true\n")
        self.assert_error('print env_get("X", default = "a", default = "b")\n', "E113")
        self.assert_error('print env_get(default = "x", "X")\n', "E114")
        self.assert_error('print trim("x", unknown = true)\n', "E207")

    def test_regex_match_search_and_errors(self):
        source = 'print regex_match("^[0-9]+$", "12345")\nprint regex_match("[0-9]+", "x1")\nprint regex_search("[0-9]+", "x1")\n'
        self.assertEqual(execute(source)[1], "true\nfalse\ntrue\n")
        self.assert_error('print regex_search("[abc", "a")\n', "E830")

    def test_regex_find_groups_all_replace_and_split(self):
        source = '''m = regex_find("([0-9]+)-([A-Z]+)", "id=12-ABC")
print regex_text(m)
print regex_start(m)
print regex_end(m)
print regex_group(m, 0)
print regex_group(m, 1)
print regex_group(m, 2)
print m.text
print m.start
print m.end
print m.group(1)
print length(regex_find_all("[A-Z]+", "AA bb CCC"))
print regex_replace("([0-9]+)", "<$1>", "a12b3")
print regex_split("[,;]", "a,b;c")
'''
        self.assertEqual(execute(source)[1], "12-ABC\n3\n9\n12-ABC\n12\nABC\n12-ABC\n3\n9\n12\n2\na<12>b<3>\n[a, b, c]\n")
        self.assertEqual(execute('print regex_find("x", "abc")\n')[1], "null\n")
        self.assert_error('print regex_group(regex_find("(a)", "a"), 2)\n', "E834")
        self.assert_error('print regex_find("(a)", "a").group(2)\n', "E834")
        self.assert_error('print regex_find("a", "a").unknown()\n', "E213")

    def test_glob_is_relative_sorted_recursive_and_empty(self):
        root = Path(__file__).resolve().parents[1]
        source = 'print glob("examples/**/*.sep")\nprint glob("none/*.sep")\n'
        output = execute(source, project_root=root)[1].splitlines()
        self.assertIn("examples/const.sep", output[0]); self.assertEqual(output[1], "[]")
        self.assert_error('print glob("../*.sep")\n', "E840")

    def test_environment_is_explicit_and_mutable_in_runtime(self):
        source = '''function:main
print env_get("MISSING")
print env_get("MISSING", default = "production")
print env_exists("MODE")
env_set("MODE", "test")
print env_get("MODE")
env_remove("MODE")
print env_exists("MODE")
end_function:main
'''
        self.assertEqual(execute(source, environment_variables={})[1], "null\nproduction\nfalse\ntest\nfalse\n")

    def test_command_line_separates_script_and_arguments(self):
        source = '''print script_path()
print command_args()
print arg_exists("-v", "--verbose")
print arg_value("--source")
print arg_value("--count", default = "1")
'''
        args = ["--source", "data", "--verbose", "--", "--count", "9"]
        self.assertEqual(execute(source, command_arguments=args, script_path="C:/app.sep")[1], "C:/app.sep\n[--source, data, --verbose, --, --count, 9]\ntrue\ndata\n1\n")

    def test_missing_and_repeated_option_values_are_errors(self):
        with self.assertRaises(SeparanError) as caught:
            execute('print arg_value("--x")\n', command_arguments=["--x"])
        self.assertEqual(caught.exception.code, "E860")
        with self.assertRaises(SeparanError) as caught:
            execute('print arg_value("--x")\n', command_arguments=["--x", "a", "--x=b"])
        self.assertEqual(caught.exception.code, "E861")


if __name__ == "__main__": unittest.main()
