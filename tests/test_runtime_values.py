import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.errors import SeparanError
from separan.interpreter import Interpreter, type_name
from separan.lexer import Lexer
from separan.parser import Parser
from separan.runtime_values import EMPTY, VOID, EmptyValue, VoidResult


def program(source):
    return Parser(Lexer(source, "values.sep").scan_tokens()).parse()


class RuntimeValueTests(unittest.TestCase):
    def test_empty_and_void_have_distinct_internal_representations(self):
        self.assertIsInstance(EMPTY, EmptyValue)
        self.assertIsInstance(VOID, VoidResult)
        self.assertIsNot(EMPTY, VOID)
        self.assertEqual(type_name(EMPTY), "EMPTY")
        self.assertEqual(type_name(VOID), "VOID")

    def test_function_fallthrough_and_bare_return_produce_void(self):
        for source in (
            "SEP:work\nEND_SEP:work\n",
            "SEP:work\nreturn\nEND_SEP:work\n",
        ):
            runtime = Interpreter()
            runtime.run(program(source), invoke_main=False)
            self.assertIs(runtime.invoke("work"), VOID)

    def test_void_cannot_be_assigned_or_printed(self):
        for statement in ("result = work()", "print work()"):
            source = f"SEP:work\nEND_SEP:work\nSEP:main\n{statement}\nEND_SEP:main\n"
            with self.subTest(statement=statement), self.assertRaises(SeparanError) as caught:
                Interpreter().run(program(source))
            self.assertIn(caught.exception.code, ("E126", "E127"))

    def test_null_source_syntax_is_rejected_with_empty_guidance(self):
        for spelling in ("null", "NULL"):
            with self.subTest(spelling=spelling), self.assertRaises(SeparanError) as caught:
                program(f"value = {spelling}\n")
            self.assertEqual(caught.exception.code, "E135")
            self.assertEqual(caught.exception.expected, "EMPTY")


if __name__ == "__main__":
    unittest.main()
