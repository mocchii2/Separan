import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.cli import execute
from separan.errors import SeparanError
from separan.interpreter import Interpreter
from separan.lexer import Lexer
from separan.parser import Parser


def program(body):
    return f"function:main\n{body}end_function:main\n"


class ListShapeOperationTests(unittest.TestCase):
    def assert_error(self, body, code):
        with self.assertRaises(SeparanError) as caught:
            execute(program(body), "shape.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_insert_supports_front_index_and_back_with_typed_empty_slots(self):
        body = '''list<number> values = [10, 20, 30]
list_insert(values, front, 2)
print values
list_insert(values, 3, 1)
print values
list_insert(values, back, 2)
print values
'''
        self.assertEqual(
            execute(program(body))[1],
            "[EMPTY, EMPTY, 10, 20, 30]\n"
            "[EMPTY, EMPTY, 10, EMPTY, 20, 30]\n"
            "[EMPTY, EMPTY, 10, EMPTY, 20, 30, EMPTY, EMPTY]\n",
        )

    def test_remove_supports_front_index_and_back_and_keeps_legacy_value_remove(self):
        body = '''list<number> values = [10, 20, 30, 40, 50]
list_remove(values, 1, 2)
print values
list_remove(values, front, 1)
print values
list_remove(values, back, 1)
print values
print list_remove([1, 2, 1], 1)
'''
        self.assertEqual(execute(program(body))[1], "[10, 40, 50]\n[40, 50]\n[40]\n[2, 1]\n")

    def test_outer_and_indexed_row_shape_operations_are_distinct(self):
        body = '''list<list<number>> values = [[1, 2], [3, 4], [5, 6]]
list_insert(values, front, 1)
print values[0] is EMPTY
list_insert(values[2], 1, 2)
print values
list_remove(values[2], 1, 2)
list_remove(values, back, 1)
print values
'''
        self.assertEqual(
            execute(program(body))[1],
            "true\n[EMPTY, [1, 2], [3, EMPTY, EMPTY, 4], [5, 6]]\n[EMPTY, [1, 2], [3, 4]]\n",
        )

    def test_horizontal_remove_changes_only_selected_row_shape(self):
        body = '''list<list<number>> values = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
list_remove_horizontal(values, 1, 1, 1)
print values
'''
        self.assertEqual(execute(program(body))[1], "[[1, 2, 3, 4], [5, 7, 8], [9, 10, 11, 12]]\n")

    def test_vertical_remove_shifts_one_column_and_preserves_outer_shape(self):
        body = '''list<list<number>> values = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
list_remove_vertical(values, 1, 1, 1)
print values
'''
        self.assertEqual(execute(program(body))[1], "[[1, 2, 3, 4], [5, 10, 7, 8], [9, EMPTY, 11, 12]]\n")

        body = '''list<list<number>> values = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
list_remove_vertical(values, 0, 1, 2)
print values
'''
        self.assertEqual(execute(program(body))[1], "[[1, 10, 3, 4], [5, EMPTY, 7, 8], [9, EMPTY, 11, 12]]\n")

    def test_jagged_vertical_validation_is_atomic(self):
        source = '''list<list<number>> values = [[1, 2, 3], [4], [5, 6, 7]]
function:main
list_remove_vertical(values, 0, 2, 2)
end_function:main
'''
        runtime = Interpreter()
        parsed = Parser(Lexer(source, "shape.sep").scan_tokens()).parse()
        with self.assertRaises(SeparanError) as caught:
            runtime.run(parsed)
        self.assertEqual(caught.exception.code, "E605")
        self.assertEqual(runtime.environment.binding("values", caught.exception.position).value, [[1, 2, 3], [4], [5, 6, 7]])

    def test_selectors_are_context_only_and_shape_ranges_are_strict(self):
        self.assert_error("value = front\n", "E136")
        self.assert_error("print back\n", "E136")
        self.assert_error("list<number> values = [1]\nlist_insert(values, front, 0)\n", "E201")
        self.assert_error("list<number> values = [1]\nlist_remove(values, 1, 1)\n", "E603")
        self.assert_error("const values = [1]\nlist_insert(values, back, 1)\n", "E211")
        self.assert_error("values = []\nlist_insert(values, front, 1)\n", "E134")

    def test_shape_operation_result_is_void(self):
        self.assert_error("list<number> values = [1]\nresult = list_insert(values, back, 1)\n", "E126")


if __name__ == "__main__": unittest.main()
