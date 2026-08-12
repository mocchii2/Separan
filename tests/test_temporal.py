import sys
import unittest
from datetime import datetime as PyDateTime, timezone as py_timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError
from separan.interpreter import Interpreter
from separan.lexer import Lexer
from separan.parser import Parser


def has_tzdb():
    try:
        ZoneInfo("America/New_York")
        return True
    except ZoneInfoNotFoundError:
        return False


class TemporalTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "temporal.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_construction_types_and_canonical_strings(self):
        source = '''a = datetime("2026-08-13T01:30:00.12+09:00")
b = local_datetime("2026-08-13T01:30:00.001")
c = timezone("+09:00")
d = duration("90m")
print a
print b
print c
print d
print type(a)
print type(b)
print type(c)
print type(d)
'''
        expected = "2026-08-13T01:30:00.120+09:00\n2026-08-13T01:30:00.001\n+09:00\n1h30m\ndatetime\nlocal_datetime\ntimezone\nduration\n"
        self.assertEqual(execute(source)[1], expected)

    def test_datetime_requires_offset_and_local_forbids_it(self):
        self.assert_error('print datetime("2026-08-13T01:30:00")\n', "E402")
        self.assert_error('print local_datetime("2026-08-13T01:30:00Z")\n', "E402")

    def test_invalid_datetime_forms(self):
        values = (
            "2026-02-30T00:00:00Z", "2026-01-01 00:00:00Z",
            "2026-01-01T00:00:60Z", "2026-01-01T00:00:00.1234Z",
            "2026-01-01T00:00:00+14:01", "2026-01-01T00:00:00-00:00",
        )
        for value in values:
            with self.subTest(value=value): self.assert_error(f'print datetime("{value}")\n', "E401" if "+14:01" not in value and "-00:00" not in value else "E403")

    def test_duration_parsing_and_normalization(self):
        source = 'print duration("0s")\nprint duration("250ms")\nprint duration("2d4h5m6s")\nprint duration("-90m")\n'
        self.assertEqual(execute(source)[1], "0ms\n250ms\n2d4h5m6s\n-1h30m\n")

    def test_invalid_duration_forms(self):
        for value in ("", "1.5h", "30m1h", "1h20h", "1 month", "1mo", "1y", "--1h"):
            with self.subTest(value=value): self.assert_error(f'print duration("{value}")\n', "E407")

    def test_temporal_arithmetic(self):
        source = '''start = datetime("2026-08-13T01:30:00+09:00")
wait = duration("30m")
print start + wait
print wait + start
print start - wait
print (start + wait) - start
print wait + duration("15m")
print wait - duration("45m")
print wait * 2
print 2 * wait
print wait / 2
print wait / duration("15m")
'''
        expected = "2026-08-13T02:00:00+09:00\n2026-08-13T02:00:00+09:00\n2026-08-13T01:00:00+09:00\n30m\n45m\n-15m\n1h\n1h\n15m\n2.0\n"
        self.assertEqual(execute(source)[1], expected)

    def test_invalid_temporal_operations(self):
        cases = (
            'datetime("2026-01-01T00:00:00Z") + datetime("2026-01-01T00:00:00Z")',
            'local_datetime("2026-01-01T00:00:00") + duration("1h")',
            'timezone("UTC") + duration("1h")',
            'duration("1s") + 1',
        )
        for expression in cases:
            with self.subTest(expression=expression): self.assert_error("print " + expression + "\n", "E408")

    def test_temporal_comparison(self):
        source = '''a = datetime("2026-01-01T09:00:00+09:00")
b = datetime("2026-01-01T00:00:00Z")
print a == b
print a >= b
print duration("2h") > duration("1h")
print local_datetime("2026-01-02T00:00:00") > local_datetime("2026-01-01T00:00:00")
'''
        self.assertEqual(execute(source)[1], "true\ntrue\ntrue\ntrue\n")
        self.assert_error('print datetime("2026-01-01T00:00:00Z") > duration("1s")\n', "E408")
        self.assert_error('print datetime("2026-01-01T00:00:00Z") == duration("0s")\n', "E408")

    def test_duration_precision_loss(self):
        self.assert_error('print duration("1ms") / 2\n', "E409")
        self.assert_error('print duration("1ms") * 0.5\n', "E409")

    def test_unix_conversions_are_unit_explicit(self):
        source = '''utc = timezone("UTC")
a = datetime("1970-01-01T00:00:01.250Z")
print unix_seconds_from_datetime(a)
print unix_milliseconds_from_datetime(a)
print datetime_from_unix_seconds(1.25, utc)
print datetime_from_unix_milliseconds(1250, utc)
'''
        self.assertEqual(execute(source)[1], "1.25\n1250\n1970-01-01T00:00:01.250Z\n1970-01-01T00:00:01.250Z\n")
        self.assert_error('print datetime_from_unix_seconds(0.0001, timezone("UTC"))\n', "E409")

    def test_fixed_offset_local_resolution_and_zone_change(self):
        source = '''wall = local_datetime("2026-08-13T01:30:00")
tokyo = timezone("+09:00")
utc = timezone("UTC")
instant = datetime_from_local(wall, tokyo)
print instant
print datetime_in_timezone(instant, utc)
'''
        self.assertEqual(execute(source)[1], "2026-08-13T01:30:00+09:00\n2026-08-12T16:30:00Z\n")

    def test_introspection(self):
        source = '''a = datetime("2026-08-13T01:30:45.123+09:00")
print datetime_year(a)
print datetime_month(a)
print datetime_day(a)
print datetime_hour(a)
print datetime_minute(a)
print datetime_second(a)
print datetime_millisecond(a)
print datetime_offset(a)
print datetime_timezone(a)
print duration_milliseconds(duration("1.250s"))
'''
        # Decimal duration components are intentionally invalid.
        with self.assertRaises(SeparanError) as caught:
            execute(source)
        self.assertEqual(caught.exception.code, "E407")
        valid = source.replace('duration("1.250s")', 'duration("1s250ms")')
        self.assertEqual(execute(valid)[1], "2026\n8\n13\n1\n30\n45\n123\n9h\n+09:00\n1250\n")

    def test_datetime_now_uses_injected_clock(self):
        source = 'print datetime_now(timezone("+09:00"))\nprint datetime_now()\nprint datetime_now("+09:00")\nprint unix_time()\n'
        program = Parser(Lexer(source, "clock.sep").scan_tokens()).parse()
        output = StringIO()
        clock = lambda: PyDateTime(2026, 8, 12, 16, 30, 0, 123456, tzinfo=py_timezone.utc)
        Interpreter(output, clock=clock).run(program)
        self.assertEqual(output.getvalue(), "2026-08-13T01:30:00.123+09:00\n2026-08-12T16:30:00.123Z\n2026-08-13T01:30:00.123+09:00\n1786552200.123\n")

    def test_parse_format_valid_weekday_and_unix_aliases(self):
        source = '''dt = datetime_parse("2026-08-13T06:30:00.125+09:00")
print datetime_format(dt, "yyyy-MM-dd HH:mm:ss.SSS XXX")
print datetime_valid(2024, 2, 29)
print datetime_valid(2026, 2, 29)
print datetime_weekday(dt)
print unix_time(datetime("1970-01-01T00:00:01.250Z"))
print datetime_from_unix(1.25)
print datetime_from_unix(1.25, "+09:00")
'''
        self.assertEqual(execute(source)[1], "2026-08-13 06:30:00.125 +09:00\ntrue\nfalse\n4\n1.25\n1970-01-01T00:00:01.250Z\n1970-01-01T09:00:01.250+09:00\n")
        self.assert_error('print datetime_format(datetime("2026-01-01T00:00:00Z"), "YYYY")\n', "E410")
        self.assert_error('print datetime_valid(2026.0, 1, 1)\n', "E201")

    def test_calendar_constructor_requires_named_timezone(self):
        source = 'print datetime(2026, 8, 13, 6, 30, 0, timezone = "+09:00")\n'
        self.assertEqual(execute(source)[1], "2026-08-13T06:30:00+09:00\n")
        self.assert_error("print datetime(2026, 8, 13, 6, 30, 0)\n", "E201")
        self.assert_error('print datetime("2026-08-13T06:30:00+09:00", timezone = "UTC")\n', "E207")

    def test_temporal_type_is_fixed(self):
        self.assert_error('x = duration("1s")\nx = datetime("2026-01-01T00:00:00Z")\n', "E201")

    def test_unknown_timezone(self):
        self.assert_error('print timezone("Not/A_Real_Zone")\n', "E403")

    def test_zero_offset_is_canonical_utc(self):
        self.assertEqual(execute('print timezone("+00:00")\nprint timezone("UTC") == timezone("+00:00")\n')[1], "UTC\ntrue\n")

    def test_four_digit_year_format_and_offset_overflow(self):
        self.assertEqual(execute('print datetime("0001-01-01T00:00:00Z")\nprint local_datetime("0001-01-01T00:00:00")\n')[1], "0001-01-01T00:00:00Z\n0001-01-01T00:00:00\n")
        self.assert_error('print datetime("0001-01-01T00:00:00+14:00")\n', "E401")

    def test_temporal_builtin_names_are_reserved(self):
        for name in ("datetime", "local_datetime", "timezone", "duration", "datetime_now"):
            with self.subTest(name=name):
                self.assert_error(f"function:{name}\nend_function:{name}\n", "E209")

    @unittest.skipUnless(has_tzdb(), "IANA tzdb is not installed")
    def test_iana_timezone_and_dst_diagnostics(self):
        self.assertEqual(execute('print datetime_in_timezone(datetime("2026-08-12T16:30:00Z"), timezone("Asia/Tokyo"))\n')[1], "2026-08-13T01:30:00+09:00\n")
        self.assert_error('print datetime_from_local(local_datetime("2026-03-08T02:30:00"), timezone("America/New_York"))\n', "E406")
        self.assert_error('print datetime_from_local(local_datetime("2026-11-01T01:30:00"), timezone("America/New_York"))\n', "E405")


if __name__ == "__main__":
    unittest.main()
