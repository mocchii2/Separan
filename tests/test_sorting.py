import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class SortingTests(unittest.TestCase):
    def output(self, body):
        return execute(f"function:main\n{body}end_function:main\n")[1]

    def error(self, body, code):
        with self.assertRaises(SeparanError) as caught:
            self.output(body)
        self.assertEqual(caught.exception.code, code)

    def test_ascending_descending_and_input_is_unchanged(self):
        body = '''items = [3, 1, 2]
print sort(items)
print sort_descending(items)
print items
'''
        self.assertEqual(self.output(body), "[1, 2, 3]\n[3, 2, 1]\n[3, 1, 2]\n")

    def test_unicode_casefold_sort_is_stable(self):
        body = '''items = ["b", "A", "a", "B"]
print sort_ignore_case(items)
print sort_ignore_case_descending(items)
'''
        self.assertEqual(self.output(body), "[A, a, b, B]\n[b, B, A, a]\n")

    def test_natural_sort_compares_ascii_digit_runs_numerically(self):
        body = '''items = ["file10", "file2", "file02", "file1"]
print sort_natural(items)
print sort_natural_descending(items)
print sort_natural_ignore_case(["A10", "a2", "A1"])
print sort_natural_ignore_case_descending(["A10", "a2", "A1"])
'''
        self.assertEqual(self.output(body), "[file1, file2, file02, file10]\n[file10, file2, file02, file1]\n[A1, a2, A10]\n[A10, a2, A1]\n")

    def test_temporal_values_are_orderable(self):
        body = '''items = [duration("10s"), duration("2s"), duration("5s")]
print sort(items)
print sort_descending(items)
'''
        self.assertEqual(self.output(body), "[2s, 5s, 10s]\n[10s, 5s, 2s]\n")

    def test_sort_by_object_field_and_descending_are_stable(self):
        body = '''object:a
name = "first"
score = 20
end_object:a
object:b
name = "second"
score = 10
end_object:b
object:c
name = "third"
score = 20
end_object:c
items = [a, b, c]
ascending = sort_by(items, "score")
descending = sort_by_descending(items, "score")
print ascending[0].name
print ascending[1].name
print ascending[2].name
print descending[0].name
print descending[1].name
print descending[2].name
'''
        self.assertEqual(self.output(body), "second\nfirst\nthird\nfirst\nthird\nsecond\n")

    def test_specialized_sorts_are_strict(self):
        self.error("print sort_ignore_case([1, 2])\n", "E201")
        self.error("print sort_natural([1, 2])\n", "E201")
        self.error("print sort([true, false])\n", "E201")
        self.error('print sort_by([1, 2], "value")\n', "E201")

    def test_sort_by_rejects_missing_mixed_and_unordered_fields(self):
        missing = '''object:a
name = "a"
end_object:a
object:b
value = 1
end_object:b
print sort_by([a, b], "name")
'''
        self.error(missing, "E212")
        mixed = '''object:a
key = 1
end_object:a
object:b
key = "2"
end_object:b
print sort_by([a, b], "key")
'''
        self.error(mixed, "E201")
        unordered = '''object:a
key = true
end_object:a
print sort_by([a], "key")
'''
        self.error(unordered, "E201")

    def test_sort_function_names_are_reserved_and_counts_are_checked(self):
        names = ("sort_descending", "sort_ignore_case", "sort_ignore_case_descending",
                 "sort_natural", "sort_natural_descending", "sort_natural_ignore_case",
                 "sort_natural_ignore_case_descending", "sort_by", "sort_by_descending")
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(SeparanError) as caught:
                    execute(f"function:{name}\nend_function:{name}\n")
                self.assertEqual(caught.exception.code, "E209")
        self.error("print sort_by([])\n", "E207")


if __name__ == "__main__": unittest.main()
