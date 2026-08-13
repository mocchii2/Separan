import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class OperatorTests(unittest.TestCase):
    def output(self, body):
        return execute(f"function:main\n{body}end_function:main\n")[1]

    def error(self, body, code):
        with self.assertRaises(SeparanError) as caught:
            self.output(body)
        self.assertEqual(caught.exception.code, code)

    def test_power_precedence_associativity_and_domain(self):
        self.assertEqual(self.output("print 2 ** 3 ** 2\nprint -2 ** 2\nprint 2 ** -2\n"), "512\n-4\n0.25\n")
        self.error("print (-1) ** 0.5\n", "E308")

    def test_floor_division_is_integer_and_floors_negatives(self):
        self.assertEqual(self.output("print 7 // 3\nprint -7 // 3\n"), "2\n-3\n")
        self.error("print 7.0 // 3\n", "E201")
        self.error("print 7 // 0\n", "E301")

    def test_null_coalescing_is_right_associative_and_short_circuits(self):
        source = '''function:fail
print "called"
return 9
end_function:fail
function:main
print 1 ?? fail()
print null ?? null ?? 3
end_function:main
'''
        self.assertEqual(execute(source)[1], "1\n3\n")
        self.assertEqual(self.output('print false ?? true\nprint 0 ?? 2\nprint "" ?? "fallback"\n'), "false\n0\n\n")

    def test_compound_assignments_and_type_rules(self):
        body = '''value = 2
value **= 3
value += 1
value *= 2
value //= 3
value %= 5
value -= 1
value /= 2
print value
items = [1]
items += [2, 3]
print items
'''
        self.assertEqual(self.output(body), "0.0\n[1, 2, 3]\n")
        self.error('value = 1\nvalue += "x"\n', "E201")
        self.error("const value = 1\nvalue += 1\n", "E211")
        self.error('items = [1]\nitems += ["x"]\n', "E201")

    def test_null_coalescing_assignment_is_intentionally_rejected(self):
        self.error('value = null\nvalue ??= "x"\n', "E100")

    def test_membership_for_supported_containers(self):
        body = '''print "bc" in "abcd"
print "z" not in "abcd"
print 2 in [1, 2, 3]
object:user
name = "Alice"
end_object:user
print "name" in user
data = bytes_from_hex("00FF10")
print 255 in data
print bytes_from_hex("FF10") in data
'''
        self.assertEqual(self.output(body), "true\ntrue\ntrue\ntrue\ntrue\ntrue\n")

    def test_membership_is_strict_and_comparisons_cannot_chain(self):
        self.error('print "1" in [1, 2]\n', "E201")
        self.error('print 1 in "123"\n', "E201")
        self.error('print 256 in bytes_from_hex("FF")\n', "E201")
        self.error("print 1 in [1] == true\n", "E111")

    def test_not_keyword_requires_boolean_outside_membership(self):
        self.assertEqual(self.output("print not false\n"), "true\n")
        self.error("print not 1\n", "E201")


if __name__ == "__main__": unittest.main()
