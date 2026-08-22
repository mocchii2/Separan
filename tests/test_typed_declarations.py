import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.ast_nodes import TypedDeclaration
from separan.cli import execute
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser


class TypedDeclarationTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "typed.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_scalar_declarations_and_reassignment(self):
        source = '''number count = 1
string name = "Separan"
boolean active = true
count = 2
print count
print name
print active
'''
        self.assertEqual(execute(source)[1], "2\nSeparan\ntrue\n")

    def test_declaration_has_dedicated_ast_node(self):
        program = Parser(Lexer('string name = "Separan"\n', "typed.sep").scan_tokens()).parse()
        declaration = program.statements[0]
        self.assertIsInstance(declaration, TypedDeclaration)
        self.assertEqual((declaration.declared_type, declaration.name), ("string", "name"))
        self.assertFalse(declaration.constant)

    def test_declared_type_must_match_initializer(self):
        error = self.assert_error('number count = "1"\n', "E201")
        self.assertEqual(error.expected, "number")
        self.assertEqual(error.actual, "string")

    def test_initializer_is_required(self):
        error = self.assert_error("string name\n", "E124")
        self.assertIn("requires an initial value", error.description)

    def test_typed_list_keeps_element_type_when_initially_empty(self):
        self.assertEqual(execute("list<number> values = []\nvalues = [1, 2]\nprint values\n")[1], "[1, 2]\n")
        self.assert_error('list<number> values = []\nvalues = ["x"]\n', "E201")
        self.assert_error('list<number> values = ["x"]\n', "E201")

    def test_typed_list_requires_element_type(self):
        self.assert_error("list values = []\n", "E124")

    def test_typed_const_is_read_only(self):
        program = Parser(Lexer('const string name = "Separan"\n', "typed.sep").scan_tokens()).parse()
        self.assertTrue(program.statements[0].constant)
        self.assert_error('const string name = "Separan"\nname = "Other"\n', "E211")

    def test_typed_declaration_cannot_redeclare_local_binding(self):
        self.assert_error("number value = 1\nnumber value = 2\n", "E210")
        self.assert_error("value = 1\nnumber value = 2\n", "E210")


if __name__ == "__main__":
    unittest.main()
