import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class CollectionAndMathBuiltinTests(unittest.TestCase):
    def error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "collection_math.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_trigonometric_logarithmic_and_exponential_functions(self):
        source = '''print sin(0)
print cos(0)
print tan(0)
print log(1)
print log10(1000)
print log2(8)
print exp(0)
'''
        self.assertEqual(execute(source)[1], "0.0\n1.0\n0.0\n0.0\n3.0\n3.0\n1.0\n")
        self.assertAlmostEqual(float(execute("print sin(1)\n")[1]), math.sin(1))

    def test_math_types_domains_and_finite_results_are_strict(self):
        for call in ('sin("0")', "cos(true)", "log(null)"):
            with self.subTest(call=call): self.error(f"print {call}\n", "E201")
        for call in ("log(0)", "log(-1)", "log10(0)", "log2(-1)", "exp(10000)"):
            with self.subTest(call=call): self.error(f"print {call}\n", "E308")

    def test_function_references_map_and_builtin_callback(self):
        source = '''function:double(x)
return x * 2
end_function:double
function:main
callback = double
print type_of(callback)
print map([1, 2, 3], callback)
print map([-2, 3], abs)
end_function:main
'''
        self.assertEqual(execute(source)[1], "function\n[2, 4, 6]\n[2, 3]\n")

    def test_map_requires_homogeneous_results(self):
        source = '''function:mixed(value)
if value == 1 :first
return 1
else:first
return "two"
endif:first
end_function:mixed
function:main
print map([1, 2], mixed)
end_function:main
'''
        self.error(source, "E203")
        self.error("print map([1], 1)\n", "E201")
        self.error("print map([], 1)\n", "E201")

    def test_filter_requires_boolean_predicate(self):
        source = '''function:is_large(value)
return value >= 10
end_function:is_large
function:main
print filter([5, 10, 20], is_large)
end_function:main
'''
        self.assertEqual(execute(source)[1], "[10, 20]\n")
        self.error("print filter([], null)\n", "E201")
        invalid = '''function:identity(value)
return value
end_function:identity
print filter([1], identity)
'''
        self.error(invalid, "E201")

    def test_reduce_requires_initial_and_preserves_accumulator_type(self):
        source = '''function:add(total, value)
return total + value
end_function:add
function:main
print reduce([1, 2, 3], add, 0)
print reduce([], add, 10)
end_function:main
'''
        self.assertEqual(execute(source)[1], "6\n10\n")
        changed = '''function:change(total, value)
return "changed"
end_function:change
print reduce([1], change, 0)
'''
        self.error(changed, "E201")
        self.error("print reduce([], 1, 0)\n", "E201")
        self.error("print reduce([], 0)\n", "E207")

    def test_flatten_removes_exactly_one_level(self):
        self.assertEqual(execute("print flatten([[1, 2], [], [3]])\nprint flatten([])\n")[1], "[1, 2, 3]\n[]\n")
        self.assertEqual(execute("print flatten([[[1]], [[2]]])\n")[1], "[[1], [2]]\n")
        self.error("print flatten([1, 2])\n", "E201")
        self.error('print flatten([[1], ["x"]])\n', "E203")

    def test_sum_average_and_count(self):
        source = '''print sum([10, 20, 30])
print sum([])
print average([10, 20, 30])
print count([1, 2, 1, 1], 1)
print count([], "anything")
'''
        self.assertEqual(execute(source)[1], "60\n0\n20.0\n3\n0\n")
        self.error("print average([])\n", "E602")
        self.error('print sum(["1"])\n', "E201")
        self.error('print average(["1"])\n', "E201")
        self.error('print count([1], "1")\n', "E201")

    def test_type_predicates_are_exact_and_never_truthy(self):
        source = '''object:item
value = 1
end_object:item
print is_number(1)
print is_number(true)
print is_string("x")
print is_boolean(false)
print is_list([])
print is_object(item)
print is_null(null)
print is_bytes(bytes_from_hex("00"))
print is_datetime(datetime("2026-08-13T00:00:00Z"))
print is_duration(duration("1s"))
print is_secret("not a secret")
'''
        self.assertEqual(execute(source)[1], "true\nfalse\ntrue\ntrue\ntrue\ntrue\ntrue\ntrue\ntrue\ntrue\nfalse\n")

    def test_reverse_char_at_and_literal_find_all_are_unicode_strict(self):
        source = '''print reverse("abc日本")
print reverse([1, 2, 3])
print char_at("日本語", 1)
print find_all("banana", "an")
print find_all("aaaa", "aa")
print find_all("abc", "x")
'''
        self.assertEqual(execute(source)[1], "本日cba\n[3, 2, 1]\n本\n[1, 3]\n[0, 2]\n[]\n")
        self.error('print char_at("abc", 3)\n', "E302")
        self.error('print char_at("abc", -1)\n', "E201")
        self.error('print find_all("abc", "")\n', "E305")

    def test_new_names_are_reserved_and_argument_counts_checked(self):
        names = ("sin", "cos", "tan", "log", "log10", "log2", "exp", "map", "filter", "reduce",
                 "flatten", "sum", "average", "count", "char_at", "find_all", "is_number", "is_string",
                 "is_boolean", "is_list", "is_object", "is_bytes", "is_datetime", "is_duration", "is_secret")
        for name in names:
            with self.subTest(name=name):
                self.error(f"function:{name}\nend_function:{name}\n", "E209")
        for call in ("map([])", "filter([])", "flatten([], 1)", "sum()", "average([], 1)", "count([])", 'char_at("x")', 'find_all("x")'):
            with self.subTest(call=call): self.error(f"print {call}\n", "E207")


if __name__ == "__main__": unittest.main()
