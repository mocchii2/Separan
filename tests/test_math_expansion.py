import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.builtins import BUILTINS
from separan.cli import execute
from separan.errors import SeparanError
from separan.interpreter import Interpreter
from separan.token import SourcePosition


class ExpandedMathTests(unittest.TestCase):
    def error(self, call, code):
        with self.assertRaises(SeparanError) as caught:
            execute(f"print {call}\n", "math.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_readable_basic_numeric_operations(self):
        source = '''print absolute(-4.5)
print minimum([3, 1, 2])
print minimum(3, 1, 2)
print maximum([3, 1, 2])
print maximum(3, 1, 2)
print round(1.235, 2)
print round(-1.25, 1)
print round(125, -1)
print truncate(-3.8)
print clamp(12, 0, 10)
print clamp(-2, 0, 10)
print sign(-10)
print sign(0)
print sign(2.5)
'''
        self.assertEqual(execute(source)[1], "4.5\n1\n1\n3\n3\n1.24\n-1.3\n130\n-3\n10\n0\n-1\n0\n1\n")

    def test_roots_powers_exponentials_and_logs(self):
        source = '''print square_root(16)
print cube_root(-27)
print power(2, 10)
print hypotenuse(3, 4)
print exponential(0)
print exponential_base2(3)
print natural_log(1)
print log_base2(8)
print log_base10(1000)
print log_one_plus(0)
'''
        self.assertEqual(execute(source)[1], "4.0\n-3.0\n1024\n5.0\n1.0\n8.0\n0.0\n3.0\n3.0\n0.0\n")

    def test_trigonometric_hyperbolic_and_angle_functions(self):
        source = '''print is_close(arc_sin(sin(0.5)), 0.5)
print is_close(arc_cos(cos(0.5)), 0.5)
print is_close(arc_tan(tan(0.5)), 0.5)
print is_close(arc_tan2(1, 1), to_radians(45))
print is_close(to_degrees(to_radians(90)), 90)
print is_close(arc_sinh(sinh(0.5)), 0.5)
print is_close(arc_cosh(cosh(0.5)), 0.5)
print is_close(arc_tanh(tanh(0.5)), 0.5)
'''
        self.assertEqual(execute(source)[1], "true\n" * 8)

    def test_integer_math(self):
        source = '''print greatest_common_divisor(54, 24)
print greatest_common_divisor(-54, 24)
print least_common_multiple(54, 24)
print factorial(0)
print factorial(5.0)
print is_integer_value(5)
print is_integer_value(5.0)
print is_integer_value(5.5)
'''
        self.assertEqual(execute(source)[1], "6\n6\n216\n1\n120\ntrue\ntrue\nfalse\n")

    def test_large_integer_rounding_and_closeness_do_not_leak_python_overflow(self):
        source = '''large = power(10, 400)
print length(string(round(large, 2)))
print is_close(large, large)
'''
        self.assertEqual(execute(source)[1], "401\ntrue\n")

    def test_numeric_state_predicates_accept_non_finite_host_values(self):
        runtime = Interpreter()
        position = SourcePosition("host.sep", 1, 1, "value")
        self.assertTrue(BUILTINS["is_finite"].call([10], position, runtime))
        self.assertFalse(BUILTINS["is_finite"].call([float("inf")], position, runtime))
        self.assertTrue(BUILTINS["is_infinite"].call([float("-inf")], position, runtime))
        self.assertTrue(BUILTINS["is_nan"].call([float("nan")], position, runtime))
        self.assertFalse(BUILTINS["is_nan"].call([0], position, runtime))

    def test_statistics_and_monitoring_math(self):
        source = '''print median([4, 1, 3, 2])
print median([3, 1, 2])
print is_close(variance([1, 2, 3]), 0.6666666666666666)
print sample_variance([1, 2, 3])
print is_close(standard_deviation([1, 2, 3]), 0.816496580927726)
print sample_standard_deviation([1, 2, 3])
print percentile([1, 2, 3, 4], 0)
print percentile([1, 2, 3, 4], 25)
print percentile([1, 2, 3, 4], 100)
print moving_average([1, 2, 3, 4], 2)
'''
        self.assertEqual(execute(source)[1], "2.5\n2\ntrue\n1\ntrue\n1.0\n1\n1.75\n4\n[1.5, 2.5, 3.5]\n")

    def test_explicit_base_conversions(self):
        source = '''print number_to_binary(10)
print number_to_octal(493)
print number_to_hexadecimal(255)
print number_to_hexadecimal(-255)
print binary_to_number("1010")
print octal_to_number("755")
print hexadecimal_to_number("ff")
print hexadecimal_to_number("FF_FF")
print number_to_base(35, 36)
print base_to_number("z", 36)
'''
        self.assertEqual(execute(source)[1], "1010\n755\nff\n-ff\n10\n493\n255\n65535\nz\n35\n")

    def test_math_type_errors_are_explicit(self):
        for call in (
            'absolute("1")', 'maximum("1")', 'round(1, "2")',
            'truncate(true)', 'clamp(1, 0, "2")', 'sign(null)', 'square_root("4")',
            'power(2, true)', 'hypotenuse([], 2)', 'factorial(2.5)', 'median("1")',
            'moving_average([1], 1.5)', 'number_to_base(1.5, 10)', 'base_to_number(10, 10)',
        ):
            with self.subTest(call=call):
                self.error(call, "E201")
        self.error('minimum([1, "2"])', "E203")

    def test_math_domain_and_collection_errors_are_explicit(self):
        for call in (
            'clamp(1, 10, 0)', 'square_root(-1)', 'power(-1, 0.5)', 'natural_log(0)',
            'log_base10(-1)', 'arc_sin(2)', 'arc_cos(-2)', 'arc_cosh(0.5)', 'arc_tanh(1)',
            'factorial(-1)', 'factorial(1001)', 'percentile([1], -1)', 'percentile([1], 101)',
            'moving_average([1, 2], 0)', 'moving_average([1, 2], 3)', 'number_to_base(1, 1)',
            'number_to_base(1, 37)', 'base_to_number("1", 1)', 'round(1, 101)',
        ):
            with self.subTest(call=call):
                self.error(call, "E308")
        for call in ('minimum([])', 'maximum([])', 'median([])', 'variance([])', 'sample_variance([1])', 'sample_standard_deviation([1])', 'moving_average([], 1)'):
            with self.subTest(call=call):
                self.error(call, "E602")

    def test_invalid_base_text_is_a_conversion_error(self):
        for call in (
            'binary_to_number("")', 'binary_to_number("102")', 'binary_to_number("0b10")',
            'octal_to_number("8")', 'hexadecimal_to_number("0xff")', 'base_to_number("z", 35)',
            'base_to_number("_10", 2)', 'base_to_number("10_", 2)', 'base_to_number("1__0", 2)',
        ):
            with self.subTest(call=call):
                self.error(call, "E304")


class NumericLiteralTests(unittest.TestCase):
    def error(self, source, code="E101"):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "numbers.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_binary_octal_hexadecimal_and_separators(self):
        source = '''print 0b1010
print 0B1111_0000
print 0o755
print 0O7_5_5
print 0xff
print 0XFF_FF
print 1_000_000
print 12_345.67_89
print -0b1010
'''
        self.assertEqual(execute(source)[1], "10\n240\n493\n493\n255\n65535\n1000000\n12345.6789\n-10\n")

    def test_invalid_numeric_separators_and_digits(self):
        values = (
            "1_", "1__0", "0b", "0b_1", "0b1_", "0b10__01", "0b102",
            "0o", "0o_7", "0o8", "0x", "0x_ff", "0xff_", "0xfg",
            "1._0", "1.0_", "1.0__1",
        )
        for value in values:
            with self.subTest(value=value):
                diagnostic = self.error(f"print {value}\n")
                self.assertEqual((diagnostic.position.line, diagnostic.position.column), (1, 7))

    def test_lf_and_crlf_produce_identical_line_numbers(self):
        lf = 'print 0b1\nprint 0b2\n'
        crlf = lf.replace("\n", "\r\n")
        lf_error = self.error(lf)
        crlf_error = self.error(crlf)
        self.assertEqual((lf_error.position.line, lf_error.position.column), (2, 7))
        self.assertEqual((crlf_error.position.line, crlf_error.position.column), (2, 7))
        self.assertEqual(lf_error.position.source_line, crlf_error.position.source_line)


if __name__ == "__main__":
    unittest.main()
