import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class ListBuiltinTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "lists.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_append_is_non_destructive(self):
        source = '''items = [1, 2, 3]
added = list_append(items, 4)
print items
print added
'''
        self.assertEqual(execute(source)[1], "[1, 2, 3]\n[1, 2, 3, 4]\n")

    def test_append_establishes_empty_list_element_type(self):
        self.assertEqual(execute('items = []\nitems = list_append(items, 1)\nitems = list_append(items, 2)\nprint items\n')[1], "[1, 2]\n")
        self.assert_error('items = []\nitems = list_append(items, 1)\nitems = list_append(items, "x")\n', "E201")

    def test_remove_first_is_non_destructive(self):
        source = '''items = [1, 2, 1]
removed = list_remove(items, 1)
print items
print removed
'''
        self.assertEqual(execute(source)[1], "[1, 2, 1]\n[2, 1]\n")

    def test_remove_missing_is_explicit_error(self):
        self.assert_error("print list_remove([1, 2], 3)\n", "E604")

    def test_size_first_and_last(self):
        self.assertEqual(execute('print size([10, 20, 30])\nprint first([10, 20, 30])\nprint last([10, 20, 30])\nprint size([])\n')[1], "3\n10\n30\n0\n")
        self.assert_error("print first([])\n", "E602")
        self.assert_error("print last([])\n", "E602")

    def test_contains_supports_string_and_list_without_coercion(self):
        source = 'print contains([10, 20], 20)\nprint contains([10, 20], 30)\nprint contains([10, 20], null)\nprint contains("Separan", "para")\n'
        self.assertEqual(execute(source)[1], "true\nfalse\nfalse\ntrue\n")
        self.assert_error('print contains([1, 2], "1")\n', "E201")

    def test_index_of_returns_number_or_null(self):
        source = 'print index_of(["a", "b", "a"], "a")\nprint last_index_of(["a", "b", "a"], "a")\nprint index_of(["a", "b"], "x")\nprint last_index_of(["a"], "x")\nprint index_of([], 10)\n'
        self.assertEqual(execute(source)[1], "0\n2\nnull\nnull\nnull\n")

    def test_slice_is_half_open_and_non_destructive(self):
        source = 'items = [10, 20, 30, 40]\npart = slice(items, 1, 3)\nprint items\nprint part\nprint slice(items, 2, 2)\n'
        self.assertEqual(execute(source)[1], "[10, 20, 30, 40]\n[20, 30]\n[]\n")

    def test_slice_range_is_strict(self):
        for call, code in (
            ("slice([1], -1, 1)", "E201"), ("slice([1], 0.5, 1)", "E201"),
            ("slice([1], 1, 0)", "E603"), ("slice([1], 0, 2)", "E603"),
        ):
            with self.subTest(call=call): self.assert_error("print " + call + "\n", code)

    def test_reverse_and_sort_are_non_destructive(self):
        source = '''items = [3, 1, 2]
print reverse(items)
print sort(items)
print items
print sort(["b", "a", "c"])
'''
        self.assertEqual(execute(source)[1], "[2, 1, 3]\n[1, 2, 3]\n[3, 1, 2]\n[a, b, c]\n")

    def test_sort_rejects_non_ordered_types(self):
        for value in ('[true, false]', '[null]', '[[1], [2]]'):
            with self.subTest(value=value): self.assert_error(f"print sort({value})\n", "E201")

    def test_operations_require_lists_and_matching_types(self):
        cases = (
            ('print list_append([1], "x")\n', "E201"),
            ('print list_remove([1], "1")\n', "E201"),
            ('print size("abc")\n', "E201"), ('print first(1)\n', "E201"),
            ('print index_of([1], "1")\n', "E201"), ('print reverse(null)\n', "E201"),
        )
        for source, code in cases:
            with self.subTest(source=source): self.assert_error(source, code)

    def test_argument_counts_and_reserved_names(self):
        calls = ("list_append([])", "list_remove([])", "size()", "first([], 1)", "last()", "index_of([])", "slice([], 0)", "reverse()", "sort([], 1)")
        for call in calls:
            with self.subTest(call=call): self.assert_error("print " + call + "\n", "E207")
        for name in ("list_append", "list_remove", "size", "length", "is_empty", "first", "last", "index_of", "last_index_of", "slice", "reverse", "sort", "repeat", "pad_left", "pad_right"):
            with self.subTest(name=name):
                self.assert_error(f"function:{name}\nend_function:{name}\n", "E209")

    def test_readable_non_mutating_list_names(self):
        source = '''items = [1, 2, 1]
print append(items, 3)
print prepend(items, 0)
print remove(items, 1)
print remove_at(items, 1)
print unique(items)
print items
'''
        self.assertEqual(execute(source)[1], "[1, 2, 1, 3]\n[0, 1, 2, 1]\n[2, 1]\n[1, 1]\n[1, 2]\n[1, 2, 1]\n")
        self.assert_error("print remove_at([1], 1)\n", "E603")

    def test_type_of_and_is_null_are_explicit(self):
        self.assertEqual(execute('print type_of([])\nprint is_null(null)\nprint is_null(0)\n')[1], "list\ntrue\nfalse\n")


if __name__ == "__main__":
    unittest.main()
