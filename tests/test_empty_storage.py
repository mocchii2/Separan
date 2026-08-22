import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class EmptyStorageTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "empty-storage.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_typed_variable_can_start_empty_and_retains_type(self):
        source = '''number age = EMPTY
print age is EMPTY
print type_of(age)
age = 30
print age is not EMPTY
age = EMPTY
print age is EMPTY
age = 31
print age
'''
        self.assertEqual(execute(source)[1], "true\nnumber\ntrue\ntrue\n31\n")
        self.assert_error('number age = EMPTY\nage = "30"\n', "E201")

    def test_untyped_empty_and_empty_constant_are_rejected(self):
        self.assert_error("value = EMPTY\n", "E129")
        self.assert_error("const number value = EMPTY\n", "E130")
        self.assert_error("const value = EMPTY\n", "E130")

    def test_empty_cannot_be_used_as_a_concrete_value(self):
        cases = (
            "number value = EMPTY\nprint value\n",
            "number value = EMPTY\nprint value + 1\n",
            "function:main\nboolean value = EMPTY\nif value :present\nendif:present\nend_function:main\n",
            "string value = EMPTY\nprint upper(value)\n",
        )
        for source in cases:
            with self.subTest(source=source):
                self.assert_error(source, "E131")

    def test_typed_parameter_accepts_empty_without_losing_type(self):
        source = '''function:show_age(age: number)
if age is EMPTY :missing
return "missing"
endif:missing
return string(age)
end_function:show_age
function:main
print show_age(EMPTY)
print show_age(30)
end_function:main
'''
        self.assertEqual(execute(source)[1], "missing\n30\n")

    def test_untyped_parameter_requires_empty_with_retained_type(self):
        direct = 'function:check(value)\nreturn value is EMPTY\nend_function:check\nprint check(EMPTY)\n'
        self.assert_error(direct, "E129")
        retained = 'function:check(value)\nreturn value is EMPTY\nend_function:check\nnumber source = EMPTY\nprint check(source)\n'
        self.assertEqual(execute(retained)[1], "true\n")

    def test_typed_object_field_can_be_empty_and_updated_non_destructively(self):
        source = '''object:user
string name = EMPTY
number age = 30
end_object:user
print user.name is EMPTY
print type_of(user.name)
updated = object_set(user, "name", "Alice")
print updated.name
cleared = object_set(updated, "name", EMPTY)
print cleared.name is EMPTY
print user.name is EMPTY
'''
        self.assertEqual(execute(source)[1], "true\nstring\nAlice\ntrue\ntrue\n")
        self.assert_error('object:user\nstring name = EMPTY\nend_object:user\nbad = object_set(user, "name", 1)\n', "E201")
        self.assert_error('object:user\nname = EMPTY\nend_object:user\n', "E129")
        self.assert_error('object:user\nname = "Alice"\nend_object:user\nbad = object_set(user, "new", EMPTY)\n', "E129")


if __name__ == "__main__":
    unittest.main()
