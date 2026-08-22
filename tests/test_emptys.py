import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))

from separan.ast_nodes import EmptysTestExpr, IndexAssignment, PrintStmt
from separan.cli import execute
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser


def parse(source):
    return Parser(Lexer(source, "emptys.sep").scan_tokens()).parse()


class EmptysTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "emptys.sep")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_index_assignment_has_a_dedicated_ast_node(self):
        statement = parse("values[1] = EMPTY\n").statements[0]
        self.assertIsInstance(statement, IndexAssignment)
        self.assertEqual(statement.name, "values")

    def test_list_slots_retain_element_type_while_empty(self):
        source = '''list<number> values = [1, 2, 3]
values[1] = EMPTY
print values[1] is EMPTY
print type_of(values[1])
print values
values[1] = 4
print values
'''
        self.assertEqual(execute(source)[1], "true\nnumber\n[1, EMPTY, 3]\n[1, 4, 3]\n")

    def test_list_literals_can_mix_typed_empty_and_concrete_elements(self):
        self.assertEqual(execute("list<number> values = [EMPTY, 1]\nprint values\n")[1], "[EMPTY, 1]\n")
        self.assertEqual(execute("values = [1, EMPTY]\nprint type_of(values[1])\n")[1], "number\n")
        self.assert_error("values = [EMPTY, EMPTY]\n", "E134")

    def test_index_assignment_checks_bounds_const_and_element_type(self):
        self.assert_error("values = [1]\nvalues[1] = EMPTY\n", "E302")
        self.assert_error('values = [1]\nvalues[0] = "x"\n', "E201")
        self.assert_error("const values = [1]\nvalues[0] = EMPTY\n", "E211")
        self.assert_error("values = [1]\nvalues[0] = EMPTYS\n", "E133")
        self.assert_error("list<number> values = [1, EMPTY]\nsorted = sort(values)\n", "E131")

    def test_emptys_clears_list_values_without_removing_slots(self):
        source = '''list<number> values = [1, 2, 3]
values = EMPTYS
print values is EMPTYS
print length(values)
print values
values[0] = 0
print values is not EMPTYS
'''
        self.assertEqual(execute(source)[1], "true\n3\n[EMPTY, EMPTY, EMPTY]\ntrue\n")

    def test_empty_list_is_emptys_and_typed_emptys_can_initialize_it(self):
        statement = parse("print values is EMPTYS\n").statements[0]
        self.assertIsInstance(statement, PrintStmt)
        self.assertIsInstance(statement.value, EmptysTestExpr)
        self.assertEqual(execute("list<number> values = EMPTYS\nprint values is EMPTYS\nprint length(values)\n")[1], "true\n0\n")

    def test_emptys_requires_a_container(self):
        self.assert_error("number value = 1\nvalue = EMPTYS\n", "E133")
        self.assert_error("value = EMPTYS\n", "E133")
        self.assert_error("object value = EMPTYS\n", "E133")

    def test_emptys_preserves_object_fields_and_nested_list_slots(self):
        source = '''object:user
string name = "Alice"
number age = 30
list<number> scores = [10, 20]
end_object:user
user = EMPTYS
print user is EMPTYS
print user.name is EMPTY
print type_of(user.name)
print length(user.scores)
print user.scores is EMPTYS
'''
        self.assertEqual(execute(source)[1], "true\ntrue\nstring\n2\ntrue\n")

    def test_object_set_can_clear_a_container_field(self):
        source = '''object:data
list<number> values = [1, 2]
end_object:data
cleared = object_set(data, "values", EMPTYS)
print length(cleared.values)
print cleared.values is EMPTYS
'''
        self.assertEqual(execute(source)[1], "2\ntrue\n")


if __name__ == "__main__":
    unittest.main()
