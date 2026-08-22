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
            "function:work\nend_function:work\n",
            "function:work\nreturn\nend_function:work\n",
        ):
            runtime = Interpreter()
            runtime.run(program(source), invoke_main=False)
            self.assertIs(runtime.invoke("work"), VOID)

    def test_void_cannot_be_assigned_or_printed(self):
        for statement in ("result = work()", "print work()"):
            source = f"function:work\nend_function:work\nfunction:main\n{statement}\nend_function:main\n"
            with self.subTest(statement=statement), self.assertRaises(SeparanError) as caught:
                Interpreter().run(program(source))
            self.assertIn(caught.exception.code, ("E126", "E127"))

    def test_legacy_null_remains_separate_during_migration(self):
        self.assertIsNone(program("value = null\n").statements[0].value.value)
        self.assertNotEqual(type_name(None), type_name(EMPTY))


if __name__ == "__main__":
    unittest.main()
