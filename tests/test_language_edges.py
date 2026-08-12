import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser
from separan.token import SourcePosition


def parse(source): return Parser(Lexer(source, "edge.sep").scan_tokens()).parse()


class SyntaxAndDiagnosticTests(unittest.TestCase):
    def assert_code(self, source, code):
        with self.assertRaises(SeparanError) as caught: parse(source)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_label_case_is_significant(self):
        self.assert_code('function:main\nif true :Check\nendif:check\nend_function:main\n', "E104")

    def test_branch_label_mismatches(self):
        for branch in ('elseif false :wrong', 'else:wrong'):
            with self.subTest(branch=branch):
                self.assert_code(f'function:main\nif true :right\n{branch}\nendif:right\nend_function:main\n', "E104")

    def test_invalid_branch_order(self):
        sources = [
            'function:main\nif true :x\nelse:x\nelse:x\nendif:x\nend_function:main\n',
            'function:main\nif true :x\nelse:x\nelseif false :x\nendif:x\nend_function:main\n']
        for source in sources:
            with self.subTest(source=source): self.assert_code(source, "E108")

    def test_duplicate_open_labels_across_kinds(self):
        self.assert_code('function:main\nif true :main\nendif:main\nend_function:main\n', "E109")

    def test_unexpected_closer_kinds(self):
        for closer in ('endif:x', 'endwhile:x', 'endfor:x', 'end_function:x'):
            with self.subTest(closer=closer): self.assert_code(closer + '\n', "E107")

    def test_unclosed_block_kinds(self):
        sources = [
            'function:main\n',
            'function:main\nif true :x\n',
            'function:main\nwhile true :x\n',
            'function:main\nfor x in [] :items\n']
        for source in sources:
            with self.subTest(source=source): self.assert_code(source, "E106")

    def test_main_parameter_and_duplicate_function(self):
        with self.assertRaisesRegex(SeparanError, "zero parameters"): execute('function:main(x)\nend_function:main\n')
        with self.assertRaisesRegex(SeparanError, "already defined"): execute('function:f\nend_function:f\nfunction:f\nend_function:f\n')

    def test_return_top_level_and_control_top_level(self):
        for statement in ('return 1', 'if true :x', 'while true :x', 'for x in [] :x'):
            with self.subTest(statement=statement): self.assert_code(statement + '\n', "E110")

    def test_source_positions_are_exact(self):
        self.assertNotEqual(SourcePosition("x", 1, 2, " x"), SourcePosition("x", 1, 3, " x"))

    def test_elseif_position_is_keyword_position(self):
        program = parse('function:main\nif false :x\n  elseif true :x\nendif:x\nend_function:main\n')
        branch = program.statements[0].body[0].branches[1]
        self.assertEqual((branch.position.line, branch.position.column), (3, 3))


class RuntimeEdgeTests(unittest.TestCase):
    def assert_runtime_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: execute(source)
        self.assertEqual(caught.exception.code, code)

    def test_null_comparisons(self):
        source = 'function:main\nx = 1\nprint x != null\ny = null\nprint y == null\nend_function:main\n'
        self.assertEqual(execute(source)[1], "true\ntrue\n")

    def test_heterogeneous_equality_rejected(self):
        for expression in ('1 == "1"', 'true != 1', '[] == 1'):
            with self.subTest(expression=expression): self.assert_runtime_error('print ' + expression + '\n', "E201")

    def test_list_index_errors(self):
        for index in ('-1', '0.5', '2'):
            code = "E302" if index == '2' else "E201"
            with self.subTest(index=index): self.assert_runtime_error(f'x = [1]\nprint x[{index}]\n', code)

    def test_zero_division_and_modulo(self):
        for operator in ('/', '%'):
            with self.subTest(operator=operator): self.assert_runtime_error(f'print 1 {operator} 0\n', "E301")

    def test_short_circuit(self):
        self.assertEqual(execute('print false && missing\nprint true || missing\n')[1], "false\ntrue\n")

    def test_undefined_names_and_argument_count(self):
        self.assert_runtime_error('print missing\n', "E202")
        self.assert_runtime_error('print missing()\n', "E206")
        self.assert_runtime_error('function:f(x)\nreturn x\nend_function:f\nprint f()\n', "E207")

    def test_implicit_null_return(self):
        self.assertEqual(execute('function:f\nend_function:f\nprint f() == null\n')[1], "true\n")

    def test_empty_list_parameter_can_gain_element_type(self):
        source = 'function:f(x)\nreturn x\nend_function:f\nfunction:main\nprint f([])\nprint f([1])\nprint f([2])\nend_function:main\n'
        self.assertEqual(execute(source)[1], "[]\n[1]\n[2]\n")

    def test_parameter_list_element_type_is_fixed(self):
        source = 'function:f(x)\nreturn x\nend_function:f\nfunction:main\nprint f([1])\nprint f(["x"])\nend_function:main\n'
        self.assert_runtime_error(source, "E208")

    def test_empty_list_parameter_element_type_becomes_fixed(self):
        source = 'function:f(x)\nreturn x\nend_function:f\nfunction:main\nprint f([])\nprint f([1])\nprint f(["x"])\nend_function:main\n'
        self.assert_runtime_error(source, "E208")

    def test_explicitly_grouped_comparisons_are_allowed(self):
        self.assertEqual(execute('print (1 < 2) == true\nprint 1 == (2 - 1)\n')[1], "true\ntrue\n")


class LexerEdgeTests(unittest.TestCase):
    def assert_lex_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: Lexer(source, "lex.sep").scan_tokens()
        self.assertEqual(caught.exception.code, code)

    def test_unterminated_string(self): self.assert_lex_error('print "x\n', "E103")
    def test_invalid_escape(self): self.assert_lex_error('print "\\q"\n', "E101")
    def test_unterminated_comment(self): self.assert_lex_error('::note\ntext\n', "E106")
    def test_comment_label_mismatch(self): self.assert_lex_error('::note\ntext\n::other\n', "E104")
    def test_non_ascii_identifier(self): self.assert_lex_error('名前 = 1\n', "E101")
    def test_supported_escapes(self):
        self.assertEqual(execute('print "a\\n\\r\\t\\\"\\\\"\n')[1], 'a\n\r\t"\\\n')


if __name__ == "__main__": unittest.main()
