"""Broad negative conformance coverage for syntax, runtime, and built-in APIs."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.builtins import BUILTINS
from separan.cli import execute
from separan.errors import SeparanError


FILENAME = "negative.sep"


def assert_failure(testcase, source, expected_code):
    with testcase.assertRaises(SeparanError) as caught:
        execute(source, FILENAME)
    diagnostic = caught.exception
    testcase.assertEqual(diagnostic.code, expected_code)
    testcase.assertEqual(diagnostic.position.file, FILENAME)
    testcase.assertGreaterEqual(diagnostic.position.line, 1)
    testcase.assertGreaterEqual(diagnostic.position.column, 1)
    lines = source.splitlines()
    if diagnostic.position.line <= len(lines):
        testcase.assertEqual(diagnostic.position.source_line, lines[diagnostic.position.line - 1])
    testcase.assertIn(
        f"--> {FILENAME}:{diagnostic.position.line}:{diagnostic.position.column}",
        str(diagnostic),
    )
    return diagnostic


SYNTAX_CASES = (
    ("unexpected_dollar", "print $\n", "E100"),
    ("unexpected_brace", "print {\n", "E100"),
    ("unterminated_string", 'print "value\n', "E103"),
    ("unknown_escape", 'print "\\q"\n', "E219"),
    ("short_unicode_escape", 'print "\\u123"\n', "E220"),
    ("non_hex_unicode_escape", 'print "\\uZZZZ"\n', "E220"),
    ("surrogate_unicode_escape", 'print "\\uD800"\n', "E220"),
    ("oversized_unicode_escape", 'print "\\U00110000"\n', "E220"),
    ("dangling_decimal_point", "print 1.\n", "E101"),
    ("unicode_variable", "名前 = 1\n", "E101"),
    ("decomposed_unicode_label", "function:main\nif true :cafe\u0301\nendif:cafe\u0301\nend_function:main\n", "E102"),
    ("unterminated_comment", "##note\nignored\n", "E106"),
    ("comment_label_mismatch", "##note\nignored\n##other\n", "E104"),
    ("bare_function_tag", "function:main\n@\nend_function:main\n", "E216"),
    ("tag_outside_function", "@notification\nfunction:main\nend_function:main\n", "E216"),
    ("tag_after_statement", 'function:main\nprint "x"\n@notification\nend_function:main\n', "E217"),
    ("duplicate_function_tag", "function:main\n@notification\n@notification\nend_function:main\n", "E218"),
    ("incomplete_structural_token", "function:main\n:end\nend_function:main\n", "E122"),
    ("return_at_top_level", "return 1\n", "E110"),
    ("if_at_top_level", "if true :condition\nendif:condition\n", "E110"),
    ("while_at_top_level", "while true :loop\nendwhile:loop\n", "E110"),
    ("for_at_top_level", "for item in [] :items\nendfor:items\n", "E110"),
    ("try_at_top_level", "try :work\nfinally:work\nendtry:work\n", "E110"),
    ("transaction_at_top_level", "transaction db :work\nend_transaction:work\n", "E110"),
    ("throw_at_top_level", 'throw runtime_error("bad")\n', "E110"),
    ("nested_function", "function:main\nfunction:child\nend_function:child\nend_function:main\n", "E110"),
    ("nested_import", 'function:main\nimport "child.sep" as child\nend_function:main\n', "E703"),
    ("late_import", 'value = 1\nimport "child.sep" as child\n', "E702"),
    ("nested_error_declaration", "function:main\nerror:child_error\nend_error:child_error\nend_function:main\n", "E120"),
    ("error_name_without_suffix", "error:failure\nend_error:failure\n", "E121"),
    ("lowercase_route_method", 'http_route get "/" :home\nend_http_route:home\n', "E891"),
    ("unsupported_route_method", 'http_route OPTIONS "/" :home\nend_http_route:home\n', "E891"),
    ("relative_route_path", 'http_route GET "users" :users\nend_http_route:users\n', "E892"),
    ("route_path_with_query", 'http_route GET "/users?q=1" :users\nend_http_route:users\n', "E892"),
    ("route_path_with_fragment", 'http_route GET "/users#top" :users\nend_http_route:users\n', "E892"),
    ("invalid_object_entry", "object:item\nprint 1\nend_object:item\n", "E115"),
    ("duplicate_object_field", "object:item\nname = 1\nname = 2\nend_object:item\n", "E116"),
    ("duplicate_catch", "function:main\ntry :work\ncatch io_error :work\ncatch io_error :work\nendtry:work\nend_function:main\n", "E117"),
    ("catch_after_any", "function:main\ntry :work\ncatch any :work\ncatch io_error :work\nendtry:work\nend_function:main\n", "E118"),
    ("try_without_handler", "function:main\ntry :work\nendtry:work\nend_function:main\n", "E119"),
    ("duplicate_parameter", "function:work(value, value)\nend_function:work\n", "E112"),
    ("duplicate_named_argument", "print missing(value = 1, value = 2)\n", "E113"),
    ("positional_after_named", "print missing(value = 1, 2)\n", "E114"),
    ("chained_equal", "function:main\nif 1 == 1 == 1 :condition\nendif:condition\nend_function:main\n", "E111"),
    ("chained_not_equal", "function:main\nif 1 != 2 != 3 :condition\nendif:condition\nend_function:main\n", "E111"),
    ("chained_less", "function:main\nif 1 < 2 < 3 :condition\nendif:condition\nend_function:main\n", "E111"),
    ("mixed_comparison_chain", "function:main\nif 1 < 2 == true :condition\nendif:condition\nend_function:main\n", "E111"),
    ("second_else", "function:main\nif true :choice\nelse:choice\nelse:choice\nendif:choice\nend_function:main\n", "E108"),
    ("elseif_after_else", "function:main\nif true :choice\nelse:choice\nelseif false :choice\nendif:choice\nend_function:main\n", "E108"),
    ("unexpected_endif", "endif:missing\n", "E107"),
    ("unexpected_endwhile", "endwhile:missing\n", "E107"),
    ("unexpected_endfor", "endfor:missing\n", "E107"),
    ("unexpected_end_function", "end_function:missing\n", "E107"),
    ("unclosed_function", "function:main\n", "E106"),
    ("unclosed_if", "function:main\nif true :condition\n", "E106"),
    ("unclosed_while", "function:main\nwhile true :loop\n", "E106"),
    ("unclosed_for", "function:main\nfor item in [] :items\n", "E106"),
    ("if_label_mismatch", "function:main\nif true :right\nendif:wrong\nend_function:main\n", "E104"),
    ("elseif_label_mismatch", "function:main\nif false :right\nelseif true :wrong\nendif:right\nend_function:main\n", "E104"),
    ("else_label_mismatch", "function:main\nif false :right\nelse:wrong\nendif:right\nend_function:main\n", "E104"),
    ("while_kind_mismatch", "function:main\nwhile true :loop\nendif:loop\nend_function:main\n", "E105"),
    ("nested_block_wrong_order", "function:main\nif true :outer\nwhile true :inner\nendif:outer\nendwhile:inner\nend_function:main\n", "E105"),
    ("duplicate_open_label", "function:main\nif true :main\nendif:main\nend_function:main\n", "E109"),
    ("reserved_system_assignment", "system = 1\n", "E215"),
    ("reserved_system_parameter", "function:work(system)\nend_function:work\n", "E215"),
    ("immutable_system_member", 'system.os = "linux"\n', "E214"),
)


RUNTIME_CASES = (
    ("number_reassigned_string", 'value = 1\nvalue = "one"\n', "E201"),
    ("boolean_reassigned_number", "value = true\nvalue = 1\n", "E201"),
    ("list_element_type_changed", 'values = [1]\nvalues = ["one"]\n', "E201"),
    ("heterogeneous_list", 'print [1, "two"]\n', "E203"),
    ("undefined_variable", "print missing\n", "E202"),
    ("undefined_function", "print missing()\n", "E206"),
    ("duplicate_function", "function:work\nend_function:work\nfunction:work\nend_function:work\n", "E204"),
    ("main_with_parameter", "function:main(value)\nend_function:main\n", "E205"),
    ("builtin_redefinition", "function:length\nend_function:length\n", "E209"),
    ("duplicate_const_binding", "const value = 1\nconst value = 2\n", "E210"),
    ("const_reassignment", "const value = 1\nvalue = 2\n", "E211"),
    ("missing_object_field", "object:item\nname = 1\nend_object:item\nprint item.missing\n", "E212"),
    ("member_access_on_number", "value = 1\nprint value.name\n", "E201"),
    ("unknown_regex_method", 'match = regex_find("(a)", "a")\nprint match.missing()\n', "E213"),
    ("user_function_too_few", "function:work(value)\nreturn value\nend_function:work\nprint work()\n", "E207"),
    ("user_function_too_many", "function:work(value)\nreturn value\nend_function:work\nprint work(1, 2)\n", "E207"),
    ("user_function_named_argument", "function:work(value)\nreturn value\nend_function:work\nprint work(value = 1)\n", "E207"),
    ("parameter_type_changed", 'function:echo(value)\nreturn value\nend_function:echo\nprint echo(1)\nprint echo("one")\n', "E208"),
    ("if_condition_not_boolean", "function:main\nif 1 :condition\nendif:condition\nend_function:main\n", "E201"),
    ("while_condition_not_boolean", "function:main\nwhile 1 :loop\nendwhile:loop\nend_function:main\n", "E201"),
    ("for_target_not_list", "function:main\nfor item in 1 :items\nendfor:items\nend_function:main\n", "E201"),
    ("index_target_not_list", 'print "abc"[0]\n', "E201"),
    ("negative_list_index", "print [1][-1]\n", "E201"),
    ("fractional_list_index", "print [1][0.5]\n", "E201"),
    ("list_index_out_of_range", "print [1][1]\n", "E302"),
    ("heterogeneous_equality", 'print 1 == "1"\n', "E201"),
    ("string_number_addition", 'print "1" + 1\n', "E201"),
    ("boolean_arithmetic", "print true + 1\n", "E201"),
    ("unary_minus_string", 'print -"1"\n', "E201"),
    ("logical_and_number", "print 1 && true\n", "E201"),
    ("logical_or_string", 'print "yes" || false\n', "E201"),
    ("division_by_zero", "print 1 / 0\n", "E301"),
    ("floor_division_by_zero", "print 1 // 0\n", "E301"),
    ("modulo_by_zero", "print 1 % 0\n", "E301"),
    ("fractional_floor_division", "print 3.5 // 2\n", "E201"),
    ("power_complex_result", "print (-1) ** 0.5\n", "E308"),
    ("throw_non_error", "function:main\nthrow 1\nend_function:main\n", "E201"),
    ("uncaught_custom_error", 'error:payment_error\nend_error:payment_error\nfunction:main\nthrow payment_error("declined")\nend_function:main\n', "E760"),
    ("duplicate_error_name", "error:payment_error\nend_error:payment_error\nerror:payment_error\nend_error:payment_error\n", "E122"),
    ("duplicate_http_route", 'http_route GET "/" :first\nend_http_route:first\nhttp_route GET "/" :second\nend_http_route:second\n', "E896"),
)


class SyntaxNegativeConformanceTests(unittest.TestCase):
    pass


class RuntimeNegativeConformanceTests(unittest.TestCase):
    pass


class BuiltinContractNegativeTests(unittest.TestCase):
    pass


def make_failure_test(source, code):
    def test(self):
        assert_failure(self, source, code)
    return test


def make_builtin_test(name, arguments, category):
    source = f"print {name}({', '.join(arguments)})\n"

    def test(self):
        diagnostic = assert_failure(self, source, "E207")
        self.assertEqual(diagnostic.category, category)
        self.assertEqual((diagnostic.position.line, diagnostic.position.column), (1, 7))
    return test


for case_name, source, code in SYNTAX_CASES:
    setattr(SyntaxNegativeConformanceTests, f"test_{case_name}", make_failure_test(source, code))

for case_name, source, code in RUNTIME_CASES:
    setattr(RuntimeNegativeConformanceTests, f"test_{case_name}", make_failure_test(source, code))

for builtin_name, builtin in sorted(BUILTINS.items()):
    if builtin.minimum_arguments:
        too_few = ["null"] * (builtin.minimum_arguments - 1)
        setattr(
            BuiltinContractNegativeTests,
            f"test_{builtin_name}_rejects_too_few_arguments",
            make_builtin_test(builtin_name, too_few, "Argument count mismatch"),
        )
    too_many = ["null"] * (builtin.maximum_arguments + 1)
    setattr(
        BuiltinContractNegativeTests,
        f"test_{builtin_name}_rejects_too_many_arguments",
        make_builtin_test(builtin_name, too_many, "Argument count mismatch"),
    )
    setattr(
        BuiltinContractNegativeTests,
        f"test_{builtin_name}_rejects_unknown_named_argument",
        make_builtin_test(builtin_name, ["unexpected = null"], "Unknown named argument" if hasattr(builtin, "named") else "Unsupported named argument"),
    )


if __name__ == "__main__":
    unittest.main()
