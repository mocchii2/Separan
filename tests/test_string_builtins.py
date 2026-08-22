import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class StringBuiltinTests(unittest.TestCase):
    def assert_error(self, call, code):
        with self.assertRaises(SeparanError) as caught:
            execute("print " + call + "\n", "strings.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_case_and_trim(self):
        source = 'print trim("  Separan \\t")\nprint upper("Separan")\nprint lower("SEPARAN")\n'
        self.assertEqual(execute(source)[1], "Separan\nSEPARAN\nseparan\n")

    def test_unicode_case_and_length(self):
        source = 'print upper("café")\nprint lower("ÄBC")\nprint len("日本語")\nprint length("日本語")\n'
        self.assertEqual(execute(source)[1], "CAFÉ\näbc\n3\n3\n")

    def test_string_predicates(self):
        source = 'print contains("Separan", "para")\nprint contains("Separan", "python")\nprint starts_with("Separan", "Sep")\nprint ends_with("Separan", "ran")\n'
        self.assertEqual(execute(source)[1], "true\nfalse\ntrue\ntrue\n")

    def test_split_and_join(self):
        source = 'parts = split("a,b,c", ",")\nprint parts\nprint join(parts, "-")\nprint join([], ",")\n'
        self.assertEqual(execute(source)[1], "[a, b, c]\na-b-c\n\n")

    def test_replace(self):
        self.assertEqual(execute('print replace("one two one", "one", "1")\n')[1], "1 two 1\n")

    def test_substring_uses_code_point_indexes(self):
        source = 'print substring("Separan", 0, 4)\nprint substring("Separan", 4)\nprint substring("日本語", 1, 3)\nprint substring("abc", 1, 1)\n'
        self.assertEqual(execute(source)[1], "Sepa\nran\n本語\n\n")

    def test_clip_utf8_never_splits_a_code_point(self):
        source = '''print clip_utf8("abc", 10)
print clip_utf8("A日本B", 7)
print clip_utf8("日本", 5)
print clip_utf8("日本", 0)
'''
        self.assertEqual(execute(source)[1], "abc\nA日本\n日\n\n")
        for call in ('clip_utf8(1, 3)', 'clip_utf8("x", -1)', 'clip_utf8("x", 1.5)'):
            with self.subTest(call=call):
                self.assert_error(call, "E201")

    def test_string_functions_reject_implicit_conversion(self):
        calls = (
            "trim(1)", "upper(true)", "lower(null)", 'contains("x", 1)',
            'starts_with([], "x")', 'ends_with("x", false)',
            'split(1, ",")', 'join("a", ",")', 'join([1, 2], ",")',
            'join(["a"], 1)', 'replace("a", "a", 1)', "substring(1, 0)",
            'clip_utf8(1, 1)',
        )
        for call in calls:
            with self.subTest(call=call): self.assert_error(call, "E201")

    def test_empty_delimiters_are_rejected(self):
        self.assert_error('split("abc", "")', "E305")
        self.assert_error('replace("abc", "", "x")', "E305")

    def test_substring_range_is_strict(self):
        for call, code in (
            ('substring("abc", -1)', "E201"),
            ('substring("abc", 1.5)', "E201"),
            ('substring("abc", 2, 1)', "E306"),
            ('substring("abc", 0, 4)', "E306"),
        ):
            with self.subTest(call=call): self.assert_error(call, code)

    def test_argument_counts_and_reserved_names(self):
        for call in ("trim()", 'contains("x")', 'split("x")', 'join([])', 'replace("x", "x")', 'substring("x")', 'substring("x", 0, 1, 2)', 'clip_utf8("x")', 'clip_utf8("x", 1, 2)'):
            with self.subTest(call=call): self.assert_error(call, "E207")
        for name in ("trim", "upper", "lower", "contains", "starts_with", "ends_with", "split", "join", "replace", "substring", "clip_utf8"):
            with self.subTest(name=name):
                with self.assertRaises(SeparanError) as caught:
                    execute(f"function:{name}\nend_function:{name}\n")
                self.assertEqual(caught.exception.code, "E209")

    def test_string_indexes_return_number_or_null(self):
        source = 'print index_of("日本語日本", "日本")\nprint last_index_of("日本語日本", "日本")\nprint index_of("abc", "x")\nprint last_index_of("abc", "x")\n'
        self.assertEqual(execute(source)[1], "0\n3\nnull\nnull\n")
        self.assert_error('index_of("abc", "")', "E305")
        self.assert_error('last_index_of("abc", "")', "E305")

    def test_repeat_is_unicode_and_strict(self):
        self.assertEqual(execute('print repeat("ab", 3)\nprint repeat("日", 2)\nprint repeat("x", 0)\n')[1], "ababab\n日日\n\n")
        for call in ('repeat("x", -1)', 'repeat("x", 1.5)', 'repeat(1, 2)'):
            with self.subTest(call=call): self.assert_error(call, "E201")
        self.assert_error('repeat("ab", 600000)', "E607")

    def test_padding_uses_target_code_point_length(self):
        source = 'print pad_left("7", 3, "0")\nprint pad_right("日", 3, "・")\nprint pad_left("long", 2)\nprint pad_right("x", 3)\n'
        self.assertEqual(execute(source)[1], "007\n日・・\nlong\nx  \n")
        for call, code in (
            ('pad_left("x", -1)', "E201"), ('pad_right("x", 1.5)', "E201"),
            ('pad_left("x", 2, "")', "E606"), ('pad_right("x", 2, "ab")', "E606"),
            ('pad_left("x", 1048577)', "E607"),
        ):
            with self.subTest(call=call): self.assert_error(call, code)

    def test_length_and_empty_are_shared(self):
        source = 'print length("abc")\nprint length([1, 2])\nprint length(secure_random_bytes(3))\nprint is_empty("")\nprint is_empty([])\nprint is_empty(secure_random_bytes(0))\nprint is_empty("x")\n'
        self.assertEqual(execute(source)[1], "3\n2\n3\ntrue\ntrue\ntrue\nfalse\n")
        for call in ("length(1)", "is_empty(null)"):
            with self.subTest(call=call): self.assert_error(call, "E201")

    def test_compare_search_parts_and_occurrences(self):
        source = '''print compare("a", "b")
print compare("same", "same")
print compare("z", "a")
print compare_ignore_case("Straße", "STRASSE")
print substring_before("abc:def", ":")
print substring_after("abc:def", ":")
print substring_after("abc", "x")
print count_occurrences("aaaa", "aa")
'''
        self.assertEqual(execute(source)[1], "-1\n0\n1\n0\nabc\ndef\nnull\n2\n")
        for call in ('substring_before("abc", "")', 'substring_after("abc", "")', 'count_occurrences("abc", "")'):
            with self.subTest(call=call): self.assert_error(call, "E305")

    def test_format_is_positional_strict_and_escaped(self):
        source = 'print format("name={}, count={}", "Separan", 3)\nprint format("{{{}}}", true)\n'
        self.assertEqual(execute(source)[1], "name=Separan, count=3\n{true}\n")
        for call in ('format("{}")', 'format("plain", 1)', 'format("{")'):
            with self.subTest(call=call): self.assert_error(call, "E307")


if __name__ == "__main__":
    unittest.main()
