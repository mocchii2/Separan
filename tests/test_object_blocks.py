import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
from separan.cli import execute
from separan.errors import SeparanError


class ObjectBlockTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: execute(source, "objects.sep")
        self.assertEqual(caught.exception.code, code)

    def test_object_nested_object_and_list(self):
        source = '''object:user
name = "Alice"
age = 30
object:address
city = "Tokyo"
end_object:address
list:roles
"admin"
"author"
end_list:roles
end_object:user
print user.name
print user.address.city
print user.roles[1]
'''
        self.assertEqual(execute(source)[1], "Alice\nTokyo\nauthor\n")

    def test_block_list_is_homogeneous(self):
        self.assert_error('list:items\n1\n"x"\nend_list:items\n', "E203")

    def test_duplicate_and_missing_fields_are_errors(self):
        self.assert_error('object:x\na = 1\na = 2\nend_object:x\n', "E116")
        self.assert_error('object:x\na = 1\nend_object:x\nprint x.b\n', "E212")

    def test_object_api_is_non_mutating(self):
        source = '''object:user
name = "Alice"
end_object:user
updated = object_set(user, "name", "Bob")
print user.name
print updated.name
print object_has(user, "age")
print object_keys(updated)
'''
        self.assertEqual(execute(source)[1], "Alice\nBob\nfalse\n[name]\n")

    def test_label_and_kind_diagnostics(self):
        self.assert_error('object:x\na = 1\nend_object:y\n', "E104")
        self.assert_error('object:x\na = 1\nend_list:x\n', "E105")


if __name__ == "__main__": unittest.main()
