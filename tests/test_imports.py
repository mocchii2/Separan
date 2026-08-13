import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
from separan.cli import execute
from separan.errors import SeparanError


class ImportTests(unittest.TestCase):
    def run_source(self, source):
        filename = ROOT / "tests" / "fixtures" / "caller.sep"
        return execute(source, str(filename), script_path=str(filename), project_root=ROOT)[1]

    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: self.run_source(source)
        self.assertEqual(caught.exception.code, code)

    def test_namespace_function_and_const(self):
        source = 'import "math.sep" as math\nprint math.add(2, 3)\nprint math.version\n'
        self.assertEqual(self.run_source(source), "5\n1\n")

    def test_imported_function_can_be_higher_order_callback(self):
        source = 'import "math.sep" as math\nprint reduce([1, 2, 3], math.add, 0)\n'
        self.assertEqual(self.run_source(source), "6\n")

    def test_imported_main_does_not_run_and_private_is_hidden(self):
        self.assertEqual(self.run_source('import "math.sep" as math\nprint "ok"\n'), "ok\n")
        self.assert_error('import "math.sep" as math\nprint math.private_value\n', "E706")

    def test_import_order_path_and_cycle(self):
        self.assert_error('print "x"\nimport "math.sep" as math\n', "E702")
        self.assert_error('import "../outside.sep" as outside\n', "E704")
        self.assert_error('import "cycle_a.sep" as cycle\n', "E701")

    def test_module_exports_custom_error_constructor(self):
        source = '''import "math.sep" as math
function:main
try :math_failure
throw math.math_error("failed")
catch math_error :math_failure
print "caught"
endtry:math_failure
end_function:main
'''
        self.assertEqual(self.run_source(source), "caught\n")


if __name__ == "__main__": unittest.main()
