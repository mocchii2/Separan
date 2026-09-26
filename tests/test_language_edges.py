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
        self.assert_code('SEP:main\nif true :Check\nendif:check\nEND_SEP:main\n', "E104")

    def test_unicode_labels_are_allowed_and_case_sensitive(self):
        source = '''SEP:main
if false :利用者確認
print "wrong"
elseif true :利用者確認
print "ok"
else:利用者確認
print "wrong"
endif:利用者確認
END_SEP:main
'''
        self.assertEqual(execute(source)[1], "ok\n")
        self.assert_code('SEP:main\nif true :確認\nendif:确認\nEND_SEP:main\n', "E104")

    def test_unicode_open_labels_share_duplicate_namespace(self):
        source = 'SEP:main\nif true :処理中\nwhile true :処理中\nendwhile:処理中\nendif:処理中\nEND_SEP:main\n'
        self.assert_code(source, "E109")

    def test_branch_label_mismatches(self):
        for branch in ('elseif false :wrong', 'else:wrong'):
            with self.subTest(branch=branch):
                self.assert_code(f'SEP:main\nif true :right\n{branch}\nendif:right\nEND_SEP:main\n', "E104")

    def test_invalid_branch_order(self):
        sources = [
            'SEP:main\nif true :x\nelse:x\nelse:x\nendif:x\nEND_SEP:main\n',
            'SEP:main\nif true :x\nelse:x\nelseif false :x\nendif:x\nEND_SEP:main\n']
        for source in sources:
            with self.subTest(source=source): self.assert_code(source, "E108")

    def test_duplicate_open_labels_across_kinds(self):
        self.assert_code('SEP:main\nif true :main\nendif:main\nEND_SEP:main\n', "E109")

    def test_unexpected_closer_kinds(self):
        for closer in ('endif:x', 'endwhile:x', 'endfor:x', 'END_SEP:x'):
            with self.subTest(closer=closer): self.assert_code(closer + '\n', "E107")

    def test_unclosed_block_kinds(self):
        sources = [
            'SEP:main\n',
            'SEP:main\nif true :x\n',
            'SEP:main\nwhile true :x\n',
            'SEP:main\nfor x in [] :items\n']
        for source in sources:
            with self.subTest(source=source): self.assert_code(source, "E106")

    def test_legacy_function_syntax_is_rejected(self):
        with self.assertRaises(SeparanError): parse('function:main\nend_function:main\n')

    def test_main_parameter_and_duplicate_function(self):
        with self.assertRaisesRegex(SeparanError, "zero parameters"): execute('SEP:main(x)\nEND_SEP:main\n')
        with self.assertRaisesRegex(SeparanError, "already defined"): execute('SEP:f\nEND_SEP:f\nSEP:f\nEND_SEP:f\n')

    def test_return_top_level_and_control_top_level(self):
        for statement in ('return 1', 'if true :x', 'while true :x', 'for x in [] :x'):
            with self.subTest(statement=statement): self.assert_code(statement + '\n', "E110")

    def test_source_positions_are_exact(self):
        self.assertNotEqual(SourcePosition("x", 1, 2, " x"), SourcePosition("x", 1, 3, " x"))

    def test_elseif_position_is_keyword_position(self):
        program = parse('SEP:main\nif false :x\n  elseif true :x\nendif:x\nEND_SEP:main\n')
        branch = program.statements[0].body[0].branches[1]
        self.assertEqual((branch.position.line, branch.position.column), (3, 3))

    def test_function_tags_are_ast_metadata(self):
        program = parse('SEP:notify\n@monitor:notification:decision\n@通知\nprint "ok"\nEND_SEP:notify\n')
        self.assertEqual(program.statements[0].tags, ["monitor:notification:decision", "通知"])
        self.assertEqual(execute('SEP:main\n@demo\nprint "ok"\nEND_SEP:main\n')[1], "ok\n")

    def test_function_tag_placement_and_duplicates(self):
        self.assert_code('@notification\nSEP:main\nEND_SEP:main\n', "E216")
        self.assert_code('SEP:main\nprint "x"\n@notification\nEND_SEP:main\n', "E217")
        self.assert_code('SEP:main\n@notification\n@notification\nEND_SEP:main\n', "E218")
        for tag in ("@notification:", "@notification::aws", "@notification: aws"):
            with self.subTest(tag=tag):
                self.assert_code(f"SEP:main\n{tag}\nEND_SEP:main\n", "E216")

    def test_incomplete_structural_completion_lists_open_closers(self):
        exc = self.assert_code('SEP:main\nif true :active\n:end\nendif:active\nEND_SEP:main\n', "E122")
        self.assertEqual(exc.expected, "endif:active\nEND_SEP:main")


class RuntimeEdgeTests(unittest.TestCase):
    def assert_runtime_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: execute(source)
        self.assertEqual(caught.exception.code, code)

    def test_null_syntax_is_removed(self):
        self.assert_runtime_error('print null\n', "E135")
        self.assert_runtime_error('print NULL\n', "E135")

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
        self.assert_runtime_error('SEP:f(x)\nreturn x\nEND_SEP:f\nprint f()\n', "E207")

    def test_implicit_function_completion_is_void(self):
        self.assert_runtime_error('SEP:f\nEND_SEP:f\nprint f()\n', "E127")

    def test_empty_list_parameter_can_gain_element_type(self):
        source = 'SEP:f(x)\nreturn x\nEND_SEP:f\nSEP:main\nprint f([])\nprint f([1])\nprint f([2])\nEND_SEP:main\n'
        self.assertEqual(execute(source)[1], "[]\n[1]\n[2]\n")

    def test_parameter_list_element_type_is_fixed(self):
        source = 'SEP:f(x)\nreturn x\nEND_SEP:f\nSEP:main\nprint f([1])\nprint f(["x"])\nEND_SEP:main\n'
        self.assert_runtime_error(source, "E208")

    def test_empty_list_parameter_element_type_becomes_fixed(self):
        source = 'SEP:f(x)\nreturn x\nEND_SEP:f\nSEP:main\nprint f([])\nprint f([1])\nprint f(["x"])\nEND_SEP:main\n'
        self.assert_runtime_error(source, "E208")

    def test_explicitly_grouped_comparisons_are_allowed(self):
        self.assertEqual(execute('print (1 < 2) == true\nprint 1 == (2 - 1)\n')[1], "true\ntrue\n")


class LexerEdgeTests(unittest.TestCase):
    def assert_lex_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: Lexer(source, "lex.sep").scan_tokens()
        self.assertEqual(caught.exception.code, code)

    def test_unterminated_string(self): self.assert_lex_error('print "x\n', "E103")
    def test_invalid_escape(self): self.assert_lex_error('print "\\q"\n', "E219")
    def test_unterminated_comment(self): self.assert_lex_error('##note\ntext\n', "E106")
    def test_comment_label_mismatch(self): self.assert_lex_error('##note\ntext\n##other\n', "E104")
    def test_unicode_comment_label(self):
        self.assertEqual(execute('##説明\n名前 = invalid text here\n##説明\nprint "ok"\n')[1], "ok\n")
    def test_non_normalized_unicode_label(self):
        self.assert_lex_error('SEP:main\nif true :cafe\u0301\nendif:cafe\u0301\nEND_SEP:main\n', "E102")
    def test_non_ascii_identifier(self): self.assert_lex_error('名前 = 1\n', "E101")
    def test_supported_escapes(self):
        self.assertEqual(execute('print "a\\n\\r\\t\\0\\\"\\\\\\u65E5\\U0000672C"\n')[1], 'a\n\r\t\0"\\日本\n')

    def test_raw_strings_keep_backslashes_literal(self):
        self.assertEqual(execute('print r"C:\\Program Files\\App\\logs"\n')[1], "C:\\Program Files\\App\\logs\n")

    def test_invalid_unicode_escapes(self):
        for value in ('\\u123', '\\uZZZZ', '\\U00110000', '\\uD800'):
            with self.subTest(value=value): self.assert_lex_error(f'print "{value}"\n', "E220")

    def test_hash_inside_string_is_not_a_comment(self):
        self.assertEqual(execute('print "ERROR #123" # actual comment\n')[1], "ERROR #123\n")

    def test_unlabeled_multiline_and_decorative_comments(self):
        source = '################################\n##\nignored syntax !@[]\n##\nprint "ok"\n'
        self.assertEqual(execute(source)[1], "ok\n")


if __name__ == "__main__": unittest.main()
