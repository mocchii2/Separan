#include "separan_core.h"

#include <stdio.h>
#include <string.h>

int main(void) {
    separan_result ok = separan_validate_source("SEP:main\nEND_SEP:main\n");
    if (!ok.ok) {
        fprintf(stderr, "valid case unexpectedly failed\n");
        return 1;
    }

    separan_result bad = separan_validate_source("SEP:main\nEND_SEP:wrong\n");
    if (bad.ok || bad.error_count == 0U) {
        fprintf(stderr, "invalid case unexpectedly passed\n");
        return 2;
    }

    if (bad.errors[0].line_number == 0) {
        fprintf(stderr, "error metadata missing\n");
        return 3;
    }
    if (strcmp(bad.errors[0].expected, "END_SEP:main") != 0 ||
        strcmp(bad.errors[0].actual, "END_SEP:wrong") != 0 ||
        bad.errors[0].related_line_number != 1 || bad.errors[0].related_column_number != 5) {
        fprintf(stderr, "block mismatch expected/actual metadata missing\n");
        return 9;
    }
    separan_result branch_bad = separan_validate_source(
        "SEP:main\nif true :active\nelse:wrong\nendif:active\nEND_SEP:main\n");
    if (branch_bad.ok || strcmp(branch_bad.errors[0].expected, "else:active") != 0 ||
        strcmp(branch_bad.errors[0].actual, "else:wrong") != 0 ||
        branch_bad.errors[0].related_line_number != 2 || branch_bad.errors[0].related_column_number != 10) {
        fprintf(stderr, "branch mismatch expected/actual metadata missing\n");
        return 10;
    }
    separan_result control_bad = separan_validate_source(
        "SEP:main\nif true :active\nendif:wrong\nEND_SEP:main\n");
    if (control_bad.ok || strcmp(control_bad.errors[0].expected, "endif:active") != 0 ||
        strcmp(control_bad.errors[0].actual, "endif:wrong") != 0 ||
        control_bad.errors[0].related_line_number != 2 || control_bad.errors[0].related_column_number != 10) {
        fprintf(stderr, "control mismatch expected/actual metadata missing\n");
        return 11;
    }
    separan_result kind_bad = separan_validate_source(
        "SEP:main\nif true :decision\nendwhile:decision\nEND_SEP:main\n");
    if (kind_bad.ok || strcmp(kind_bad.errors[0].code, "E105") != 0 ||
        strcmp(kind_bad.errors[0].expected, "endif:decision") != 0 ||
        strcmp(kind_bad.errors[0].actual, "endwhile:decision") != 0 ||
        kind_bad.errors[0].related_line_number != 2 ||
        kind_bad.errors[0].related_column_number != 10) {
        fprintf(stderr, "block-kind mismatch metadata missing\n");
        return 12;
    }
    separan_result nesting_bad = separan_validate_source(
        "SEP:main\nif true :outer\nwhile true :inner\nendif:outer\n"
        "endwhile:inner\nendif:outer\nEND_SEP:main\n");
    if (nesting_bad.ok || strcmp(nesting_bad.errors[0].code, "E105") != 0 ||
        strcmp(nesting_bad.errors[0].expected, "endwhile:inner") != 0 ||
        strcmp(nesting_bad.errors[0].actual, "endif:outer") != 0 ||
        nesting_bad.errors[0].related_line_number != 3 ||
        nesting_bad.errors[0].related_column_number != 13) {
        fprintf(stderr, "block-nesting mismatch metadata missing\n");
        return 13;
    }
    separan_result same_kind_nesting_bad = separan_validate_source(
        "SEP:main\nif true :outer\nif true :inner\nendif:outer\n"
        "endif:inner\nendif:outer\nEND_SEP:main\n");
    if (same_kind_nesting_bad.ok || strcmp(same_kind_nesting_bad.errors[0].code, "E105") != 0 ||
        strcmp(same_kind_nesting_bad.errors[0].expected, "endif:inner") != 0 ||
        strcmp(same_kind_nesting_bad.errors[0].actual, "endif:outer") != 0 ||
        same_kind_nesting_bad.errors[0].related_line_number != 3 ||
        same_kind_nesting_bad.errors[0].related_column_number != 10) {
        fprintf(stderr, "same-kind nesting mismatch metadata missing\n");
        return 14;
    }
    separan_result unexpected_closer = separan_validate_source("endif:missing\n");
    if (unexpected_closer.ok || strcmp(unexpected_closer.errors[0].code, "E107") != 0 ||
        unexpected_closer.errors[0].expected[0] != '\0' ||
        strcmp(unexpected_closer.errors[0].actual, "endif:missing") != 0 ||
        unexpected_closer.errors[0].line_number != 1 || unexpected_closer.errors[0].column_number != 1 ||
        unexpected_closer.errors[0].related_line_number != 0) {
        fprintf(stderr, "unexpected closer metadata missing\n");
        return 15;
    }
    separan_result unexpected_nested_closer = separan_validate_source(
        "SEP:main\nif true :active\nendwhile:missing\nendif:active\nEND_SEP:main\n");
    if (unexpected_nested_closer.ok || strcmp(unexpected_nested_closer.errors[0].code, "E107") != 0 ||
        strcmp(unexpected_nested_closer.errors[0].actual, "endwhile:missing") != 0 ||
        unexpected_nested_closer.errors[0].related_line_number != 0) {
        fprintf(stderr, "nested unexpected closer metadata missing\n");
        return 16;
    }
    separan_result unclosed_block = separan_validate_source(
        "SEP:main\nif true :active\nprint \"open\"\n");
    if (unclosed_block.ok || strcmp(unclosed_block.errors[0].code, "E106") != 0 ||
        strcmp(unclosed_block.errors[0].expected, "endif:active") != 0 ||
        unclosed_block.errors[0].actual[0] != '\0' ||
        unclosed_block.errors[0].line_number != 2 || unclosed_block.errors[0].column_number != 10 ||
        unclosed_block.errors[0].related_line_number != 2 ||
        unclosed_block.errors[0].related_column_number != 10) {
        fprintf(stderr, "unclosed block expected/related metadata missing\n");
        return 17;
    }
    separan_result duplicate_label = separan_validate_source(
        "SEP:main\nif true :same\nwhile true :same\nendwhile:same\n"
        "endif:same\nEND_SEP:main\n");
    if (duplicate_label.ok || strcmp(duplicate_label.errors[0].code, "E109") != 0 ||
        strcmp(duplicate_label.errors[0].actual, "same") != 0 ||
        duplicate_label.errors[0].related_line_number != 2 ||
        duplicate_label.errors[0].related_column_number != 10) {
        fprintf(stderr, "duplicate label actual/related metadata missing\n");
        return 18;
    }

    separan_result grammar_error = separan_validate_source("SEP:main\nprint (1 + )\nEND_SEP:main\n");
    if (grammar_error.ok || grammar_error.error_count == 0U ||
        strcmp(grammar_error.errors[0].code, "E100") != 0 ||
        grammar_error.errors[0].line_number != 2 ||
        strcmp(grammar_error.errors[0].category, "Expected expression") != 0 ||
        strcmp(grammar_error.errors[0].description, "A value or expression is required here.") != 0 ||
        strcmp(grammar_error.errors[0].actual, ")") != 0 ||
        grammar_error.errors[0].column_number != 12) {
        fprintf(stderr, "validate API did not use the shared runtime parser\n");
        return 7;
    }
    separan_result trailing_token = separan_validate_source(
        "SEP:main\nprint 1 print 2\nEND_SEP:main\n");
    if (trailing_token.ok || strcmp(trailing_token.errors[0].code, "E100") != 0 ||
        strcmp(trailing_token.errors[0].category, "Unexpected token") != 0 ||
        strcmp(trailing_token.errors[0].description, "Statements must end at the end of the line.") != 0 ||
        strcmp(trailing_token.errors[0].actual, "print") != 0 ||
        trailing_token.errors[0].line_number != 2 || trailing_token.errors[0].column_number != 9) {
        fprintf(stderr, "unexpected trailing token diagnostic details missing\n");
        return 19;
    }
    separan_result missing_parenthesis = separan_validate_source(
        "SEP:main\nprint (1\nEND_SEP:main\n");
    if (missing_parenthesis.ok || strcmp(missing_parenthesis.errors[0].code, "E100") != 0 ||
        strcmp(missing_parenthesis.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_parenthesis.errors[0].description, "Expected ')' after expression.") != 0 ||
        strcmp(missing_parenthesis.errors[0].actual, "\n") != 0 ||
        missing_parenthesis.errors[0].line_number != 2 || missing_parenthesis.errors[0].column_number != 9) {
        fprintf(stderr, "missing delimiter diagnostic details missing\n");
        return 20;
    }
    separan_result missing_call_parenthesis = separan_validate_source(
        "SEP:main\nprint length(1\nEND_SEP:main\n");
    if (missing_call_parenthesis.ok || strcmp(missing_call_parenthesis.errors[0].code, "E100") != 0 ||
        strcmp(missing_call_parenthesis.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_call_parenthesis.errors[0].description, "Expected ')' after arguments.") != 0 ||
        strcmp(missing_call_parenthesis.errors[0].actual, "\n") != 0 ||
        missing_call_parenthesis.errors[0].line_number != 2 || missing_call_parenthesis.errors[0].column_number != 15) {
        fprintf(stderr, "missing call delimiter diagnostic details missing\n");
        return 21;
    }
    separan_result missing_member_parenthesis = separan_validate_source(
        "SEP:main\nobject:user\nvalue = \"x\"\nend_object:user\n"
        "print user.member(1\nEND_SEP:main\n");
    if (missing_member_parenthesis.ok || strcmp(missing_member_parenthesis.errors[0].code, "E100") != 0 ||
        strcmp(missing_member_parenthesis.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_member_parenthesis.errors[0].description, "Expected ')' after arguments.") != 0 ||
        strcmp(missing_member_parenthesis.errors[0].actual, "\n") != 0 ||
        missing_member_parenthesis.errors[0].line_number != 5 || missing_member_parenthesis.errors[0].column_number != 20) {
        fprintf(stderr, "missing member-call delimiter diagnostic details missing\n");
        return 22;
    }
    separan_result missing_index_bracket = separan_validate_source(
        "SEP:main\nvalues = [1]\nprint values[0\nEND_SEP:main\n");
    if (missing_index_bracket.ok || strcmp(missing_index_bracket.errors[0].code, "E100") != 0 ||
        strcmp(missing_index_bracket.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_index_bracket.errors[0].description, "Expected ']' after list index.") != 0 ||
        strcmp(missing_index_bracket.errors[0].actual, "\n") != 0 ||
        missing_index_bracket.errors[0].line_number != 3 || missing_index_bracket.errors[0].column_number != 15) {
        fprintf(stderr, "missing index bracket diagnostic details missing\n");
        return 31;
    }
    separan_result missing_list_literal_bracket = separan_validate_source("print [1\n");
    if (missing_list_literal_bracket.ok || strcmp(missing_list_literal_bracket.errors[0].description, "Expected ']' after list.") != 0 ||
        strcmp(missing_list_literal_bracket.errors[0].actual, "\n") != 0) {
        fprintf(stderr, "missing list literal bracket details missing\n");
        return 32;
    }
    separan_result missing_typed_list_angle = separan_validate_source("list<number values = []\n");
    if (missing_typed_list_angle.ok || strcmp(missing_typed_list_angle.errors[0].description, "Expected '>' after list element type.") != 0 ||
        strcmp(missing_typed_list_angle.errors[0].actual, "values") != 0) {
        fprintf(stderr, "missing typed-list angle detail missing\n");
        return 33;
    }
    separan_result missing_function_colon = separan_validate_source("SEP main\nEND_SEP:main\n");
    if (missing_function_colon.ok || strcmp(missing_function_colon.errors[0].description, "Expected ':' after function.") != 0 ||
        strcmp(missing_function_colon.errors[0].actual, "main") != 0) {
        fprintf(stderr, "missing function colon detail missing\n");
        return 34;
    }
    separan_result missing_const_equal = separan_validate_source("const count 1\n");
    if (missing_const_equal.ok || strcmp(missing_const_equal.errors[0].description, "Expected '=' after constant name.") != 0 ||
        strcmp(missing_const_equal.errors[0].actual, "1") != 0) {
        fprintf(stderr, "missing const equal detail missing\n");
        return 35;
    }
    separan_result missing_import_as = separan_validate_source("import \"mod.sep\" module\n");
    if (missing_import_as.ok || strcmp(missing_import_as.errors[0].description, "Expected 'as' after import path.") != 0 ||
        strcmp(missing_import_as.errors[0].actual, "module") != 0) {
        fprintf(stderr, "missing import as detail missing\n");
        return 36;
    }
    separan_result invalid_state_test = separan_validate_source(
        "SEP:main\nif value is present :state\nendif:state\nEND_SEP:main\n");
    if (invalid_state_test.ok || strcmp(invalid_state_test.errors[0].code, "E128") != 0 ||
        strcmp(invalid_state_test.errors[0].category, "Invalid state test") != 0 ||
        strcmp(invalid_state_test.errors[0].description, "The 'is' operator is reserved for EMPTY and EMPTYS state tests.") != 0 ||
        strcmp(invalid_state_test.errors[0].expected, "EMPTY or EMPTYS") != 0 ||
        strcmp(invalid_state_test.errors[0].actual, "present") != 0) {
        fprintf(stderr, "invalid state test diagnostic details missing\n");
        return 27;
    }
    separan_result chained_comparison = separan_validate_source(
        "SEP:main\nif 1 < 2 < 3 :chain\nendif:chain\nEND_SEP:main\n");
    if (chained_comparison.ok || strcmp(chained_comparison.errors[0].code, "E111") != 0 ||
        strcmp(chained_comparison.errors[0].category, "Chained comparison") != 0 ||
        strcmp(chained_comparison.errors[0].description, "Comparison operators cannot be chained. Use && explicitly.") != 0 ||
        strcmp(chained_comparison.errors[0].actual, "<") != 0) {
        fprintf(stderr, "chained comparison diagnostic details missing\n");
        return 37;
    }
    separan_result empty_equality = separan_validate_source(
        "SEP:main\nif value == EMPTY :state\nendif:state\nEND_SEP:main\n");
    if (empty_equality.ok || strcmp(empty_equality.errors[0].code, "E128") != 0 ||
        strcmp(empty_equality.errors[0].category, "Invalid state test") != 0 ||
        strcmp(empty_equality.errors[0].description, "Use 'is EMPTY' / 'is EMPTYS' state syntax instead of equality.") != 0 ||
        strcmp(empty_equality.errors[0].expected, "is EMPTY or is EMPTYS") != 0 ||
        strcmp(empty_equality.errors[0].actual, "==") != 0) {
        fprintf(stderr, "EMPTY equality diagnostic details missing\n");
        return 38;
    }
    separan_result emptys_inequality = separan_validate_source(
        "SEP:main\nif EMPTYS != value :state\nendif:state\nEND_SEP:main\n");
    if (emptys_inequality.ok || strcmp(emptys_inequality.errors[0].code, "E128") != 0 ||
        strcmp(emptys_inequality.errors[0].category, "Invalid state test") != 0 ||
        strcmp(emptys_inequality.errors[0].description, "Use 'is EMPTY' / 'is EMPTYS' state syntax instead of equality.") != 0 ||
        strcmp(emptys_inequality.errors[0].expected, "is EMPTY or is EMPTYS") != 0 ||
        strcmp(emptys_inequality.errors[0].actual, "!=") != 0) {
        fprintf(stderr, "EMPTYS inequality diagnostic details missing\n");
        return 39;
    }
    separan_result malformed_import = separan_validate_source("import missing as module\n");
    if (malformed_import.ok || strcmp(malformed_import.errors[0].code, "E100") != 0 ||
        strcmp(malformed_import.errors[0].category, "Syntax error") != 0 ||
        strcmp(malformed_import.errors[0].description, "Expected quoted .sep path after import.") != 0 ||
        strcmp(malformed_import.errors[0].actual, "missing") != 0 ||
        malformed_import.errors[0].line_number != 1 || malformed_import.errors[0].column_number != 8) {
        fprintf(stderr, "malformed import diagnostic details missing\n");
        return 23;
    }
    separan_result missing_function_name = separan_validate_source("SEP:\nEND_SEP:main\n");
    if (missing_function_name.ok || strcmp(missing_function_name.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_function_name.errors[0].description, "Expected function name.") != 0 ||
        strcmp(missing_function_name.errors[0].actual, "\n") != 0) {
        fprintf(stderr, "missing function name diagnostic details missing\n");
        return 24;
    }
    separan_result missing_function_closer = separan_validate_source("SEP:main\nEND_SEP:\n");
    if (missing_function_closer.ok || strcmp(missing_function_closer.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_function_closer.errors[0].description, "Expected closing block label.") != 0 ||
        strcmp(missing_function_closer.errors[0].actual, "\n") != 0 ||
        missing_function_closer.errors[0].line_number != 2 || missing_function_closer.errors[0].column_number != 9) {
        fprintf(stderr, "missing function closer label diagnostic details missing\n");
        return 28;
    }
    separan_result missing_open_label = separan_validate_source(
        "SEP:main\nif true :\nendif:active\nEND_SEP:main\n");
    if (missing_open_label.ok || strcmp(missing_open_label.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_open_label.errors[0].description, "Expected block label after ':'.") != 0 ||
        strcmp(missing_open_label.errors[0].actual, "\n") != 0 ||
        missing_open_label.errors[0].line_number != 2 || missing_open_label.errors[0].column_number != 10) {
        fprintf(stderr, "missing opening label diagnostic details missing\n");
        return 29;
    }
    separan_result missing_else_label = separan_validate_source(
        "SEP:main\nif true :active\nelse:\nendif:active\nEND_SEP:main\n");
    if (missing_else_label.ok || strcmp(missing_else_label.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_else_label.errors[0].description, "Expected label after else.") != 0 ||
        strcmp(missing_else_label.errors[0].actual, "\n") != 0 ||
        missing_else_label.errors[0].line_number != 3 || missing_else_label.errors[0].column_number != 6) {
        fprintf(stderr, "missing else label diagnostic details missing\n");
        return 30;
    }
    separan_result missing_import_alias = separan_validate_source("import \"mod.sep\" as\n");
    if (missing_import_alias.ok || strcmp(missing_import_alias.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_import_alias.errors[0].description, "Expected import alias.") != 0 ||
        strcmp(missing_import_alias.errors[0].actual, "\n") != 0) {
        fprintf(stderr, "missing import alias diagnostic details missing\n");
        return 25;
    }
    separan_result missing_list_name = separan_validate_source("list:\nend_list:items\n");
    if (missing_list_name.ok || strcmp(missing_list_name.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_list_name.errors[0].description, "Expected list name.") != 0 ||
        strcmp(missing_list_name.errors[0].actual, "\n") != 0) {
        fprintf(stderr, "missing list name diagnostic details missing\n");
        return 26;
    }
    separan_result valid_path = separan_validate_path("testdata/hello.sep");
    if (!valid_path.ok) {
        fprintf(stderr, "validate_path rejected a valid source file\n");
        return 8;
    }

    separan_result duplicate = separan_validate_source(
        "SEP:main\nif true :same\nwhile true :same\nendwhile:same\nendif:same\nEND_SEP:main\n");
    if (duplicate.ok || duplicate.error_count == 0U ||
        strcmp(duplicate.errors[0].code, "E109") != 0) {
        fprintf(stderr, "duplicate label did not return a structured error\n");
        return 4;
    }

    separan_result legacy_open = separan_validate_source("function:main\nend_function:main\n");
    if (legacy_open.ok || legacy_open.error_count == 0U ||
        strcmp(legacy_open.errors[0].code, "E100") != 0) return 5;
    separan_result legacy_close = separan_validate_source("end_function :main\n");
    if (legacy_close.ok || legacy_close.error_count == 0U ||
        strcmp(legacy_close.errors[0].code, "E100") != 0) return 6;

    printf("library_api: ok\n");
    separan_result_free(&ok);
    separan_result_free(&bad);
    separan_result_free(&branch_bad);
    separan_result_free(&control_bad);
    separan_result_free(&kind_bad);
    separan_result_free(&nesting_bad);
    separan_result_free(&same_kind_nesting_bad);
    separan_result_free(&unexpected_closer);
    separan_result_free(&unexpected_nested_closer);
    separan_result_free(&unclosed_block);
    separan_result_free(&duplicate_label);
    separan_result_free(&duplicate);
    separan_result_free(&grammar_error);
    separan_result_free(&trailing_token);
    separan_result_free(&missing_parenthesis);
    separan_result_free(&missing_call_parenthesis);
    separan_result_free(&missing_member_parenthesis);
    separan_result_free(&missing_index_bracket);
    separan_result_free(&missing_list_literal_bracket);
    separan_result_free(&missing_typed_list_angle);
    separan_result_free(&missing_function_colon);
    separan_result_free(&missing_const_equal);
    separan_result_free(&missing_import_as);
    separan_result_free(&invalid_state_test);
    separan_result_free(&chained_comparison);
    separan_result_free(&empty_equality);
    separan_result_free(&emptys_inequality);
    separan_result_free(&malformed_import);
    separan_result_free(&missing_function_name);
    separan_result_free(&missing_function_closer);
    separan_result_free(&missing_open_label);
    separan_result_free(&missing_else_label);
    separan_result_free(&missing_import_alias);
    separan_result_free(&missing_list_name);
    separan_result_free(&valid_path);
    separan_result_free(&legacy_open);
    separan_result_free(&legacy_close);
    return 0;
}
