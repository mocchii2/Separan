import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class BuiltinFunctionTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "builtins.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_len_for_string_and_list(self):
        self.assertEqual(execute('print len("Separan")\nprint len([1, 2, 3])\nprint len([])\n')[1], "7\n3\n0\n")

    def test_type_returns_public_type_names(self):
        source = 'print type(1)\nprint type(1.5)\nprint type("x")\nprint type(true)\nprint type([])\nprint type(null)\n'
        self.assertEqual(execute(source)[1], "number\nnumber\nstring\nboolean\nlist\nnull\n")

    def test_abs_preserves_integer_or_float_value(self):
        self.assertEqual(execute('print abs(-4)\nprint abs(-2.5)\n')[1], "4\n2.5\n")

    def test_range_forms_and_for_loop(self):
        source = '''function:main
print range(4)
print range(2, 5)
print range(5, 0, -2)
for item in range(3) :numbers
print item
endfor:numbers
end_function:main
'''
        self.assertEqual(execute(source)[1], "[0, 1, 2, 3]\n[2, 3, 4]\n[5, 3, 1]\n0\n1\n2\n")

    def test_builtin_argument_counts(self):
        for call in ("len()", "type(1, 2)", "abs()", "range()", "range(1, 2, 3, 4)", "number()", "string()", "boolean()"):
            with self.subTest(call=call):
                self.assert_error("print " + call + "\n", "E207")

    def test_builtin_types_are_strict(self):
        for call in ("len(1)", 'abs("1")', "range(1.5)", "range(true)"):
            with self.subTest(call=call):
                self.assert_error("print " + call + "\n", "E201")

    def test_range_rejects_zero_step(self):
        error = self.assert_error("print range(0, 10, 0)\n", "E303")
        self.assertEqual(error.category, "Invalid range step")

    def test_builtin_names_cannot_be_redefined(self):
        for name in ("len", "type", "abs", "range", "number", "string", "boolean"):
            with self.subTest(name=name):
                self.assert_error(f"function:{name}\nend_function:{name}\n", "E209")

    def test_number_conversion(self):
        source = 'print number("42")\nprint number("-10.5")\nprint number(7)\nprint number(1.25)\nprint number("10") + 5\n'
        self.assertEqual(execute(source)[1], "42\n-10.5\n7\n1.25\n15\n")

    def test_number_conversion_is_strict(self):
        for value in ('"abc"', '" 42"', '"42 "', '"+42"', '".5"', '"1e3"'):
            with self.subTest(value=value): self.assert_error(f"print number({value})\n", "E304")
        for value in ("true", "null", "[]"):
            with self.subTest(value=value): self.assert_error(f"print number({value})\n", "E201")

    def test_string_conversion(self):
        source = 'print string(10)\nprint string(2.5)\nprint string(true)\nprint string(false)\nprint string(null)\nprint string("x")\n'
        self.assertEqual(execute(source)[1], "10\n2.5\ntrue\nfalse\nnull\nx\n")

    def test_string_does_not_serialize_lists(self):
        self.assert_error("print string([1, 2])\n", "E201")

    def test_boolean_conversion(self):
        source = 'print boolean("true")\nprint boolean("false")\nprint boolean(true)\n'
        self.assertEqual(execute(source)[1], "true\nfalse\ntrue\n")

    def test_boolean_conversion_rejects_truthiness(self):
        for value, code in (("1", "E201"), ("0", "E201"), ('"True"', "E304"), ('"FALSE"', "E304"), ('"abc"', "E304"), ('" true"', "E304"), ("null", "E201")):
            with self.subTest(value=value): self.assert_error(f"print boolean({value})\n", code)

    def test_explicit_math_functions(self):
        source = '''print ceil(1.2)
print floor(1.8)
print round(2.5)
print round(-2.5)
print min(3, -1, 2.5)
print max(3, -1, 2.5)
print sqrt(9)
print pow(2, 10)
'''
        self.assertEqual(execute(source)[1], "2\n1\n3\n-3\n-1\n3\n3.0\n1024\n")

    def test_math_types_domains_and_counts_are_strict(self):
        for call in ('ceil("1")', 'min(1, "2")', 'pow(2, true)'):
            with self.subTest(call=call): self.assert_error("print " + call + "\n", "E201")
        for call in ("sqrt(-1)", "pow(-1, 0.5)"):
            with self.subTest(call=call): self.assert_error("print " + call + "\n", "E308")
        for call in ("min()", "pow(2)", "round(1, 2, 3)"):
            with self.subTest(call=call): self.assert_error("print " + call + "\n", "E207")


if __name__ == "__main__":
    unittest.main()
