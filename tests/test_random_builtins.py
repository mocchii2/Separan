import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError


class RandomBuiltinTests(unittest.TestCase):
    def assert_error(self, call, code):
        with self.assertRaises(SeparanError) as caught:
            execute("print " + call + "\n", "random.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_seeded_sequence_is_language_defined(self):
        source = '''function:main
random_seed(12345)
print random_number()
print random_int(1, 100)
print random_float(0.0, 1.0)
print random_bool()
print random_pick([10, 20, 30])
print random_shuffle([1, 2, 3, 4])
print random_sample([1, 2, 3, 4], 2)
end_function:main
'''
        expected = "0.9609531075330077\n68\n0.9515492931643655\nfalse\n10\n[3, 4, 2, 1]\n[3, 4]\n"
        self.assertEqual(execute(source)[1], expected)
        self.assertEqual(execute(source)[1], expected)

    def test_seed_reset_repeats_sequence(self):
        source = '''function:main
random_seed(7)
first = random_int(1, 100000)
random_seed(7)
second = random_int(1, 100000)
print first == second
end_function:main
'''
        self.assertEqual(execute(source)[1], "true\n")

    def test_integer_endpoints_are_inclusive(self):
        self.assertEqual(execute('function:main\nrandom_seed(1)\nprint random_int(5, 5)\nprint secure_random_int(8, 8)\nend_function:main\n')[1], "5\n8\n")

    def test_float_and_number_are_half_open(self):
        source = '''function:main
random_seed(42)
print random_number() >= 0 && random_number() < 1
print random_float(-2.5, -2.0) >= -2.5 && random_float(-2.5, -2.0) < -2.0
end_function:main
'''
        self.assertEqual(execute(source)[1], "true\ntrue\n")

    def test_shuffle_is_non_destructive(self):
        source = '''function:main
random_seed(5)
items = [1, 2, 3, 4]
shuffled = random_shuffle(items)
print items
print shuffled
end_function:main
'''
        output = execute(source)[1].splitlines()
        self.assertEqual(output[0], "[1, 2, 3, 4]")
        self.assertCountEqual(output[1].strip("[]").split(", "), ["1", "2", "3", "4"])

    def test_sample_is_unique_and_non_destructive(self):
        source = '''function:main
random_seed(8)
items = [1, 2, 3, 4]
sample = random_sample(items, 3)
print items
print len(sample)
print sample
end_function:main
'''
        lines = execute(source)[1].splitlines()
        self.assertEqual(lines[:2], ["[1, 2, 3, 4]", "3"])
        values = lines[2].strip("[]").split(", ")
        self.assertEqual(len(values), len(set(values)))

    def test_empty_population_and_sample_size(self):
        self.assert_error("random_pick([])", "E502")
        for call in ("random_sample([1], -1)", "random_sample([1], 2)"):
            with self.subTest(call=call): self.assert_error(call, "E503")
        self.assertEqual(execute('function:main\nrandom_seed(1)\nprint random_sample([], 0)\nend_function:main\n')[1], "[]\n")

    def test_ranges_and_types_are_strict(self):
        for call, code in (
            ("random_int(2, 1)", "E501"), ("random_float(1, 1)", "E501"),
            ("secure_random_int(2, 1)", "E501"), ("random_int(1.0, 2)", "E201"),
            ("random_float(true, 2)", "E201"), ('random_pick("x")', "E201"),
            ("random_shuffle(1)", "E201"), ("random_sample([], 1.0)", "E201"),
            ("random_seed(1.5)", "E201"),
        ):
            with self.subTest(call=call): self.assert_error(call, code)

    def test_secure_bytes_has_dedicated_type(self):
        output = execute('print type(secure_random_bytes(16))\nprint len(secure_random_bytes(16))\nprint hex_encode(secure_random_bytes(2))\n')[1].splitlines()
        self.assertEqual(output[:2], ["bytes", "16"])
        self.assertRegex(output[2], r"^[0-9A-F]{4}$")

    def test_secure_string_is_exact_url_safe_length(self):
        output = execute('print secure_random_string(64)\n')[1].strip()
        self.assertEqual(len(output), 64)
        self.assertRegex(output, r"^[A-Za-z0-9_-]{64}$")

    def test_secure_lengths_are_bounded(self):
        for call in ("secure_random_bytes(-1)", "secure_random_string(-1)", "secure_random_bytes(1048577)", "secure_random_string(1048577)"):
            with self.subTest(call=call): self.assert_error(call, "E504")

    def test_secure_random_has_no_seed_api(self):
        self.assert_error("secure_random_seed(1)", "E206")

    def test_argument_counts_and_reserved_names(self):
        for call in ("random_number(1)", "random_bool(1)", "random_int(1)", "random_pick()", "random_sample([])", "secure_random_bytes()", "secure_random_int(1)", "secure_random_string()"):
            with self.subTest(call=call): self.assert_error(call, "E207")
        names = ("random_seed", "random_number", "random_int", "random_float", "random_bool", "random_pick", "random_shuffle", "random_sample", "secure_random_bytes", "secure_random_int", "secure_random_string")
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(SeparanError) as caught:
                    execute(f"function:{name}\nend_function:{name}\n")
                self.assertEqual(caught.exception.code, "E209")


if __name__ == "__main__":
    unittest.main()
