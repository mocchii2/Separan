import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
from separan.cli import execute
from separan.errors import SeparanError


class BytesBuiltinTests(unittest.TestCase):
    def assert_error(self, call, code):
        with self.assertRaises(SeparanError) as caught: execute("print " + call + "\n", "bytes.sep")
        self.assertEqual(caught.exception.code, code)

    def test_string_conversion_is_explicit(self):
        source = '''data = bytes_from_string("日本語", encoding = "utf-8")
print type(data)
print length(data)
print string_from_bytes(data, encoding = "utf-8")
'''
        self.assertEqual(execute(source)[1], "bytes\n9\n日本語\n")
        self.assert_error('string_from_bytes(hex_decode("FF"), encoding = "utf-8")', "E621")
        self.assert_error('bytes_from_string("x", encoding = "unknown")', "E620")

    def test_hex_and_base64_are_strict(self):
        source = '''data = bytes_from_hex("89504E470D0A1A0A")
print hex_encode(data)
encoded = base64_encode(data)
print encoded
print hex_encode(base64_decode(encoded))
'''
        self.assertEqual(execute(source)[1], "89504E470D0A1A0A\niVBORw0KGgo=\n89504E470D0A1A0A\n")
        self.assert_error('hex_decode("ABC")', "E625")
        self.assert_error('hex_decode("GG")', "E625")
        self.assert_error('base64_decode("%%%")', "E626")

    def test_get_slice_concat_and_operator(self):
        source = '''a = hex_decode("0102FF")
b = hex_decode("A0B0")
print bytes_get(a, 2)
print hex_encode(slice_bytes(a, 1, 3))
print hex_encode(bytes_concat(a, b))
print hex_encode(a + b)
'''
        self.assertEqual(execute(source)[1], "255\n02FF\n0102FFA0B0\n0102FFA0B0\n")
        self.assert_error('bytes_get(hex_decode("00"), 1)', "E622")
        self.assert_error('slice_bytes(hex_decode("0001"), 2, 1)', "E623")

    def test_bytes_and_string_never_mix_implicitly(self):
        self.assert_error('hex_decode("00") + "x"', "E201")
        self.assert_error('bytes_concat(hex_decode("00"), "x")', "E201")
        self.assert_error('string(hex_decode("00"))', "E201")


if __name__ == "__main__": unittest.main()
