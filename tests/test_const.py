import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.ast_nodes import ConstDeclaration
from separan.cli import execute
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser


class ConstTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "const.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_global_and_local_constants(self):
        source = '''const app_name = "Separan"
function:main
const max_retry = 3
retry = 0
retry = retry + 1
print app_name
print max_retry
print retry
end_function:main
'''
        self.assertEqual(execute(source)[1], "Separan\n3\n1\n")

    def test_const_is_an_ast_declaration(self):
        program = Parser(Lexer("const pi = 3.14159\n", "const.sep").scan_tokens()).parse()
        self.assertIsInstance(program.statements[0], ConstDeclaration)
        self.assertEqual(program.statements[0].name, "pi")

    def test_constant_reassignment_is_error(self):
        error = self.assert_error("const limit = 10\nlimit = 20\n", "E211")
        self.assertEqual(error.category, "Constant reassignment")
        self.assertEqual(error.related.line, 1)

    def test_local_constant_reassignment_is_error(self):
        source = 'function:main\nconst limit = 10\nlimit = 20\nend_function:main\n'
        self.assert_error(source, "E211")

    def test_duplicate_const_and_mutable_name_are_errors(self):
        self.assert_error("const value = 1\nconst value = 2\n", "E210")
        self.assert_error("value = 1\nconst value = 2\n", "E210")

    def test_const_value_keeps_normal_type_rules(self):
        self.assertEqual(execute('const values = [1, 2]\nprint values\n')[1], "[1, 2]\n")
        self.assert_error('const values = [1, "x"]\n', "E203")

    def test_function_scope_can_shadow_global_const_without_mutating_it(self):
        source = 'const value = 1\nfunction:main\nvalue = 2\nprint value\nend_function:main\nprint value\n'
        self.assertEqual(execute(source)[1], "1\n2\n")

    def test_const_requires_name_equals_and_value(self):
        for source in ("const\n", "const value\n", "const value =\n"):
            with self.subTest(source=source): self.assert_error(source, "E100")


if __name__ == "__main__":
    unittest.main()

