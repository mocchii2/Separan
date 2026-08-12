import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reference"))
from separan.cli import execute
from separan.errors import SeparanError


class ErrorHandlingTests(unittest.TestCase):
    def assert_error(self, source, code):
        with self.assertRaises(SeparanError) as caught: execute(source, "errors.sep")
        self.assertEqual(caught.exception.code, code)

    def test_throw_catch_and_finally(self):
        source = '''function:main
try :work
throw value_error("bad value")
catch value_error :work
print "caught"
finally:work
print "finished"
endtry:work
end_function:main
'''
        self.assertEqual(execute(source)[1], "caught\nfinished\n")

    def test_existing_runtime_error_is_catchable(self):
        source = '''function:main
try :divide
print 1 / 0
catch value_error :divide
print "zero"
endtry:divide
end_function:main
'''
        self.assertEqual(execute(source)[1], "zero\n")

    def test_unmatched_error_propagates_but_finally_runs(self):
        source = '''function:main
try :work
throw type_error("wrong")
catch io_error :work
print "no"
finally:work
print "cleanup"
endtry:work
end_function:main
'''
        output = []
        class Sink:
            def write(self, value): output.append(value)
        with self.assertRaises(SeparanError): execute(source, output=Sink())
        self.assertEqual("".join(output), "cleanup\n")

    def test_any_and_parser_validation(self):
        source = '''function:main
try :x
throw permission_error("denied")
catch any :x
print "any"
endtry:x
end_function:main
'''
        self.assertEqual(execute(source)[1], "any\n")
        self.assert_error('function:main\ntry :x\nprint 1\nendtry:x\nend_function:main\n', "E119")
        self.assert_error('function:main\ntry :x\nprint 1\ncatch any :x\nprint 2\ncatch value_error :x\nprint 3\nendtry:x\nend_function:main\n', "E118")

    def test_throw_requires_error_value(self):
        self.assert_error('function:main\nthrow "bad"\nend_function:main\n', "E201")

    def test_custom_error_declaration_constructor_and_catch(self):
        source = '''error:payment_error
end_error:payment_error
function:main
try :pay
throw payment_error("card declined")
catch payment_error :pay
print "payment failed"
endtry:pay
end_function:main
'''
        self.assertEqual(execute(source)[1], "payment failed\n")

    def test_runtime_error_catches_custom_error(self):
        source = '''error:domain_error
end_error:domain_error
function:main
try :domain
throw domain_error("invalid")
catch runtime_error :domain
print "runtime"
endtry:domain
end_function:main
'''
        self.assertEqual(execute(source)[1], "runtime\n")

    def test_custom_error_declaration_is_strict(self):
        self.assert_error('error:bad\nend_error:bad\n', "E121")
        self.assert_error('error:value_error\nend_error:value_error\n', "E122")
        self.assert_error('function:main\nerror:nested_error\nend_error:nested_error\nend_function:main\n', "E120")


if __name__ == "__main__": unittest.main()
