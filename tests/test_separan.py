import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.ast_nodes import ast_structural_equal
from separan.cli import execute
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser


def parse(source): return Parser(Lexer(source, "test.sep").scan_tokens()).parse()


class SeparanTests(unittest.TestCase):
    def test_main_auto_start_and_string_addition(self):
        self.assertEqual(execute('SEP:main\nname = "Separan"\nprint "Hello, " + name\nEND_SEP:main\n')[1], "Hello, Separan\n")

    def test_top_level_runs_before_main(self):
        self.assertEqual(execute('x = 2\nprint x\nSEP:main\nprint x + 3\nEND_SEP:main\n')[1], "2\n5\n")

    def test_indent_does_not_change_ast(self):
        a = parse('SEP:main\nif true :ok\nprint "yes"\nendif:ok\nEND_SEP:main\n')
        b = parse('  SEP:main\n    if true :ok\n      print "yes"\n    endif:ok\n  END_SEP:main\n')
        self.assertNotEqual(a, b)
        self.assertTrue(ast_structural_equal(a, b))

    def test_branches_and_loops(self):
        src = '''SEP:main
items = [1, 2, 3]
sum = 0
for item in items :each
sum = sum + item
endfor:each
while sum < 7 :more
sum = sum + 1
endwhile:more
if sum > 9 :choice
print "high"
elseif sum == 7 :choice
print "seven"
else:choice
print "other"
endif:choice
END_SEP:main
'''
        self.assertEqual(execute(src)[1], "seven\n")

    def test_block_errors(self):
        cases = [
            ('SEP:main\nif true :a\nendif:b\nEND_SEP:main\n', "E104"),
            ('SEP:main\nif true :a\nif true :b\nendif:a\nendif:b\nEND_SEP:main\n', "E105"),
            ('SEP:main\nif true :a\nEND_SEP:main\n', "E105"),
            ('endif:nope\n', "E107"), ('SEP:main\nif true :a\n', "E106")]
        for source, code in cases:
            with self.subTest(code=code), self.assertRaises(SeparanError) as caught: parse(source)
            self.assertEqual(caught.exception.code, code)
            self.assertIn("--> test.sep:", str(caught.exception))

    def test_diagnostic_includes_numbered_source_location(self):
        with self.assertRaises(SeparanError) as caught:
            parse('SEP:main\nif true :check\nendif:wrong\nEND_SEP:main\n')
        diagnostic = str(caught.exception)
        self.assertIn("--> test.sep:3:7", diagnostic)
        self.assertIn("3 | endif:wrong", diagnostic)
        self.assertIn("  |       ^^^^^", diagnostic)
        self.assertIn("Opened here:\n --> test.sep:2:10", diagnostic)

    def test_diagnostic_caret_accounts_for_wide_unicode(self):
        position = Lexer('print \"あ\" + true\n', "unicode.sep").scan_tokens()[2].position
        rendered = str(SeparanError("E000", "Example", "Example diagnostic.", position))
        pointer = next(line for line in rendered.splitlines() if "^" in line)
        self.assertEqual(pointer, "  | " + " " * 11 + "^")

    def test_type_safety(self):
        with self.assertRaisesRegex(SeparanError, "fixed type number"): execute('x = 1\nx = "one"\n')
        with self.assertRaisesRegex(SeparanError, "incompatible"): execute('print "1" + 2\n')
        with self.assertRaisesRegex(SeparanError, "Conditions must evaluate to boolean"): execute('SEP:main\nif 1 :bad\nendif:bad\nEND_SEP:main\n')

    def test_top_level_restrictions(self):
        with self.assertRaisesRegex(SeparanError, "Only function definitions"):
            parse('unknown()\n')
        with self.assertRaisesRegex(SeparanError, "only be defined at top level"):
            parse('SEP:main\nSEP:nested\nEND_SEP:nested\nEND_SEP:main\n')

    def test_recursion_and_list_index(self):
        src = '''SEP:fact(n)
if n == 0 :base
return 1
else:base
return n * fact(n - 1)
endif:base
END_SEP:fact
SEP:main
values = [fact(3), fact(4)]
print values[1]
END_SEP:main
'''
        self.assertEqual(execute(src)[1], "24\n")

    def test_duplicate_parameter(self):
        with self.assertRaises(SeparanError) as caught:
            parse('SEP:f(a, a)\nreturn a\nEND_SEP:f\n')
        self.assertEqual(caught.exception.code, "E112")
        self.assertEqual(caught.exception.position.column, 10)

    def test_parameter_type_is_fixed_by_first_call(self):
        source = 'SEP:echo(x)\nreturn x\nEND_SEP:echo\nSEP:main\nprint echo(1)\nprint echo("x")\nEND_SEP:main\n'
        with self.assertRaises(SeparanError) as caught: execute(source)
        self.assertEqual(caught.exception.code, "E208")

    def test_block_kind_mismatch(self):
        with self.assertRaises(SeparanError) as caught:
            parse('SEP:main\nwhile true :x\nendif:x\nEND_SEP:main\n')
        self.assertEqual(caught.exception.category, "Block kind mismatch")
        self.assertEqual(caught.exception.expected, "endwhile:x")

    def test_all_comparison_chains_are_parser_errors(self):
        for expression in ("1 == 1 == 1", "1 != 2 != 3", "1 < 2 == true", "1 == 2 < 3", "1 < 2 < 3"):
            with self.subTest(expression=expression), self.assertRaises(SeparanError) as caught:
                parse(f'SEP:main\nif {expression} :x\nendif:x\nEND_SEP:main\n')
            self.assertEqual(caught.exception.code, "E111")

    def test_comments(self):
        self.assertEqual(execute('# one\n##skip\nprint "no"\n##skip\nprint "yes" # inline\n')[1], "yes\n")
        with self.assertRaises(SeparanError) as caught: parse('##a\nignored\n##b\n')
        self.assertEqual(caught.exception.code, "E104")

    def test_list_errors(self):
        with self.assertRaisesRegex(SeparanError, "same type"): execute('x = [1, "two"]\n')
        with self.assertRaisesRegex(SeparanError, "outside a list"): execute('x = [1]\nprint x[1]\n')


if __name__ == "__main__": unittest.main()
