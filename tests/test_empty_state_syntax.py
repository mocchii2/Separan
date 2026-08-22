import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.ast_nodes import EmptyTestExpr, PrintStmt
from separan.errors import SeparanError
from separan.interpreter import Binding, Interpreter
from separan.lexer import Lexer
from separan.parser import Parser
from separan.runtime_values import EmptyValue
from separan.token import SourcePosition


def parse(source):
    return Parser(Lexer(source, "empty.sep").scan_tokens()).parse()


class EmptyStateSyntaxTests(unittest.TestCase):
    def test_is_empty_has_a_dedicated_ast_node(self):
        statement = parse("print value is EMPTY\n").statements[0]
        self.assertIsInstance(statement, PrintStmt)
        self.assertIsInstance(statement.value, EmptyTestExpr)
        self.assertFalse(statement.value.negated)

    def test_is_and_is_not_empty_are_exact_state_tests(self):
        runtime = Interpreter()
        position = SourcePosition("empty.sep", 1, 1, "value")
        runtime.globals.values["value"] = Binding(EmptyValue("number"), "number", declaration_position=position)
        runtime.run(parse("print value is EMPTY\nprint value is not EMPTY\n"), invoke_main=False)
        self.assertEqual(runtime.output.getvalue(), "true\nfalse\n")

        runtime = Interpreter()
        runtime.run(parse("number value = 0\nprint value is EMPTY\nprint value is not EMPTY\n"), invoke_main=False)
        self.assertEqual(runtime.output.getvalue(), "false\ntrue\n")

    def test_is_cannot_be_generalized_to_normal_values(self):
        for source in ("print value is 1\n", "print value is null\n", "print value is true\n"):
            with self.subTest(source=source), self.assertRaises(SeparanError) as caught:
                parse(source)
            self.assertEqual(caught.exception.code, "E128")

    def test_empty_state_comparisons_cannot_chain(self):
        for source in ("print value is EMPTY == true\n", "print value == other is EMPTY\n", "print value is EMPTY is EMPTY\n"):
            with self.subTest(source=source), self.assertRaises(SeparanError) as caught:
                parse(source)
            self.assertEqual(caught.exception.code, "E111")

    def test_equality_with_empty_is_rejected_in_favor_of_state_syntax(self):
        for source in ("print value == EMPTY\n", "print EMPTY != value\n"):
            with self.subTest(source=source), self.assertRaises(SeparanError) as caught:
                parse(source)
            self.assertEqual(caught.exception.code, "E128")


if __name__ == "__main__":
    unittest.main()
