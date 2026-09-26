#include "separan_core.h"

#include <stdio.h>
#include <stdlib.h>
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
    separan_result duplicate_parameter = separan_validate_source(
        "SEP:work(value, value)\nEND_SEP:work\n");
    if (duplicate_parameter.ok || strcmp(duplicate_parameter.errors[0].code, "E112") != 0 ||
        strcmp(duplicate_parameter.errors[0].category, "Duplicate parameter") != 0 ||
        strcmp(duplicate_parameter.errors[0].description, "Parameter 'value' is already defined.") != 0 ||
        strcmp(duplicate_parameter.errors[0].actual, "value") != 0 ||
        duplicate_parameter.errors[0].line_number != 1 || duplicate_parameter.errors[0].column_number != 17) {
        fprintf(stderr, "duplicate parameter diagnostic details missing\n");
        return 50;
    }
    separan_result *duplicate_object_field = malloc(sizeof(*duplicate_object_field));
    if (!duplicate_object_field) return 52;
    *duplicate_object_field = separan_validate_source(
        "object:item\nname = 1\nname = 2\nend_object:item\n");
    if (duplicate_object_field->ok || strcmp(duplicate_object_field->errors[0].code, "E116") != 0 ||
        strcmp(duplicate_object_field->errors[0].category, "Duplicate object field") != 0 ||
        strcmp(duplicate_object_field->errors[0].description,
               "Field 'name' is already defined in object :item.") != 0 ||
        strcmp(duplicate_object_field->errors[0].actual, "name") != 0 ||
        duplicate_object_field->errors[0].line_number != 3 || duplicate_object_field->errors[0].column_number != 1) {
        fprintf(stderr, "duplicate object field diagnostic details missing\n");
        return 51;
    }
    separan_result *argument_diagnostic = malloc(sizeof(*argument_diagnostic));
    if (!argument_diagnostic) return 53;
    *argument_diagnostic = separan_validate_source("print missing(value = 1, value = 2)\n");
    if (argument_diagnostic->ok || strcmp(argument_diagnostic->errors[0].code, "E113") != 0 ||
        strcmp(argument_diagnostic->errors[0].category, "Duplicate named argument") != 0 ||
        strcmp(argument_diagnostic->errors[0].description, "Named argument 'value' is already specified.") != 0 ||
        strcmp(argument_diagnostic->errors[0].actual, "value") != 0 ||
        argument_diagnostic->errors[0].line_number != 1 || argument_diagnostic->errors[0].column_number != 26) {
        fprintf(stderr, "duplicate named argument diagnostic details missing\n");
        return 54;
    }
    separan_result_free(argument_diagnostic);
    *argument_diagnostic = separan_validate_source(
        "object:user\nvalue = \"x\"\nend_object:user\n"
        "print user.method(value = 1, value = 2)\n");
    if (argument_diagnostic->ok || strcmp(argument_diagnostic->errors[0].code, "E113") != 0 ||
        strcmp(argument_diagnostic->errors[0].category, "Duplicate named argument") != 0 ||
        strcmp(argument_diagnostic->errors[0].description, "Named argument 'value' is already specified.") != 0 ||
        strcmp(argument_diagnostic->errors[0].actual, "value") != 0 ||
        argument_diagnostic->errors[0].line_number != 4 || argument_diagnostic->errors[0].column_number != 30) {
        fprintf(stderr, "duplicate member-call named argument diagnostic details missing\n");
        return 55;
    }
    separan_result_free(argument_diagnostic);
    *argument_diagnostic = separan_validate_source("print missing(value = 1, 2)\n");
    if (argument_diagnostic->ok || strcmp(argument_diagnostic->errors[0].code, "E114") != 0 ||
        strcmp(argument_diagnostic->errors[0].category, "Positional argument after named argument") != 0 ||
        strcmp(argument_diagnostic->errors[0].description,
               "Positional arguments must appear before named arguments.") != 0 ||
        strcmp(argument_diagnostic->errors[0].actual, "2") != 0 ||
        argument_diagnostic->errors[0].line_number != 1 || argument_diagnostic->errors[0].column_number != 26) {
        fprintf(stderr, "positional-after-named diagnostic details missing\n");
        return 56;
    }
    separan_result_free(argument_diagnostic);
    *argument_diagnostic = separan_validate_source(
        "object:user\nvalue = \"x\"\nend_object:user\n"
        "print user.method(value = 1, 2)\n");
    if (argument_diagnostic->ok || strcmp(argument_diagnostic->errors[0].code, "E114") != 0 ||
        strcmp(argument_diagnostic->errors[0].category, "Positional argument after named argument") != 0 ||
        strcmp(argument_diagnostic->errors[0].description,
               "Positional arguments must appear before named arguments.") != 0 ||
        strcmp(argument_diagnostic->errors[0].actual, "2") != 0 ||
        argument_diagnostic->errors[0].line_number != 4 || argument_diagnostic->errors[0].column_number != 30) {
        fprintf(stderr, "member-call positional-after-named diagnostic details missing\n");
        return 57;
    }
    separan_result *try_diagnostic = malloc(sizeof(*try_diagnostic));
    if (!try_diagnostic) return 58;
    *try_diagnostic = separan_validate_source(
        "SEP:main\ntry :work\ncatch io_error :work\ncatch io_error :work\n"
        "endtry:work\nEND_SEP:main\n");
    if (try_diagnostic->ok || strcmp(try_diagnostic->errors[0].code, "E117") != 0 ||
        strcmp(try_diagnostic->errors[0].category, "Duplicate catch") != 0 ||
        strcmp(try_diagnostic->errors[0].description, "Error category 'io_error' is already caught.") != 0 ||
        strcmp(try_diagnostic->errors[0].actual, "io_error") != 0 ||
        try_diagnostic->errors[0].line_number != 4 || try_diagnostic->errors[0].column_number != 7) {
        fprintf(stderr, "duplicate catch diagnostic details missing\n");
        return 59;
    }
    separan_result_free(try_diagnostic);
    *try_diagnostic = separan_validate_source(
        "SEP:main\ntry :work\ncatch any :work\ncatch io_error :work\n"
        "endtry:work\nEND_SEP:main\n");
    if (try_diagnostic->ok || strcmp(try_diagnostic->errors[0].code, "E118") != 0 ||
        strcmp(try_diagnostic->errors[0].category, "Catch after any") != 0 ||
        strcmp(try_diagnostic->errors[0].description, "catch any must be the final catch branch.") != 0 ||
        strcmp(try_diagnostic->errors[0].actual, "io_error") != 0 ||
        try_diagnostic->errors[0].line_number != 4 || try_diagnostic->errors[0].column_number != 7) {
        fprintf(stderr, "catch-after-any diagnostic details missing\n");
        return 60;
    }
    separan_result_free(try_diagnostic);
    *try_diagnostic = separan_validate_source(
        "SEP:main\ntry :work\nendtry:work\nEND_SEP:main\n");
    if (try_diagnostic->ok || strcmp(try_diagnostic->errors[0].code, "E119") != 0 ||
        strcmp(try_diagnostic->errors[0].category, "Empty try handler") != 0 ||
        strcmp(try_diagnostic->errors[0].description,
               "A try block requires at least one catch or finally branch.") != 0 ||
        try_diagnostic->errors[0].line_number != 2 || try_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "empty try handler diagnostic details missing\n");
        return 61;
    }
    separan_result *typed_diagnostic = malloc(sizeof(*typed_diagnostic));
    if (!typed_diagnostic) return 62;
    *typed_diagnostic = separan_validate_source("number count\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E124") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Initializer required") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Typed variable 'count' requires an initial value.") != 0 ||
        strcmp(typed_diagnostic->errors[0].expected, "number count = value") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "number count") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 8) {
        fprintf(stderr, "initializer required diagnostic details missing\n");
        return 63;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source("SEP:work(value:mystery)\nEND_SEP:work\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E123") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Unknown declared type") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "'mystery' is not a supported Separan type.") != 0 ||
        strcmp(typed_diagnostic->errors[0].expected, "a supported Separan type") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "mystery") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 16) {
        fprintf(stderr, "unknown declared type diagnostic details missing\n");
        return 64;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main\nerror:nested_error\nend_error:nested_error\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E120") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Nested error declaration") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Custom errors may only be declared at top level.") != 0 ||
        typed_diagnostic->errors[0].line_number != 2 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "nested error declaration diagnostic details missing\n");
        return 65;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source("error:payment\nend_error:payment\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E121") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Invalid error name") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Custom error names must end with '_error'.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "payment") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 7) {
        fprintf(stderr, "invalid error name diagnostic details missing\n");
        return 66;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "error:payment_error\nend_error:payment_error\n"
        "error:payment_error\nend_error:payment_error\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E122") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Duplicate error name") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Custom error name 'payment_error' conflicts with an existing declaration or built-in.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "payment_error") != 0 ||
        typed_diagnostic->errors[0].line_number != 3 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "duplicate error name diagnostic details missing\n");
        return 67;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(":end\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E122") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Incomplete structural completion token") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               ":end is an editor completion trigger, not executable Separan syntax.") != 0 ||
        strcmp(typed_diagnostic->errors[0].expected, "a complete block closer") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, ":end") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "incomplete structural token diagnostic details missing\n");
        return 68;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source("@notification\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E216") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Function tag outside function") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Function tags are valid only inside a function metadata area.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "@notification") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "tag outside function diagnostic details missing\n");
        return 69;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main\nprint 1\n@notification\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E217") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Function tag must appear before executable statements") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Function tags belong to the metadata area before the first executable statement.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "@notification") != 0 ||
        typed_diagnostic->errors[0].line_number != 3 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "tag after statement diagnostic details missing\n");
        return 70;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main\n@notification\n@notification\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E218") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Duplicate function tag") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Tag '@notification' is already attached to function 'main'.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "@notification") != 0 ||
        typed_diagnostic->errors[0].line_number != 3 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "duplicate function tag diagnostic details missing\n");
        return 71;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source("system = 1\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E215") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Reserved context name") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Name 'system' is reserved for a read-only runtime context.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "system") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "reserved context assignment diagnostic details missing\n");
        return 72;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source("system.os = \"linux\"\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E214") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Immutable member") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Cannot assign to read-only member 'system.os'.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "system.os") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "immutable member diagnostic details missing\n");
        return 73;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:work(system)\nEND_SEP:work\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E215") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Reserved context name") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Name 'system' is reserved for a read-only runtime context.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "system") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 10) {
        fprintf(stderr, "reserved context parameter diagnostic details missing\n");
        return 74;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main\nif true :choice\nelse:choice\nelse:choice\n"
        "endif:choice\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E108") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Invalid if branch") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "else must be the final branch and may occur only once.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "else") != 0 ||
        typed_diagnostic->errors[0].line_number != 4 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "invalid if branch diagnostic details missing\n");
        return 75;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source("return 1\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E110") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Invalid top-level statement") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Only function definitions, data blocks, const declarations, assignments, and print are allowed at top level.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "return") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "invalid top-level statement diagnostic details missing\n");
        return 76;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:work\nEND_SEP:work\nSEP:work\nEND_SEP:work\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E204") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Duplicate function") != 0 ||
        strcmp(typed_diagnostic->errors[0].description, "Function 'work' is already defined.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "work") != 0 ||
        typed_diagnostic->errors[0].line_number != 3 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "duplicate function diagnostic details missing\n");
        return 77;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main(value)\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E205") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Invalid main function") != 0 ||
        strcmp(typed_diagnostic->errors[0].description, "main must have zero parameters in v0.1.") != 0 ||
        strcmp(typed_diagnostic->errors[0].expected, "main()") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "main(value)") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "invalid main function diagnostic details missing\n");
        return 78;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:length\nEND_SEP:length\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E209") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Reserved function name") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Function 'length' is a built-in and cannot be redefined.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "length") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "reserved function name diagnostic details missing\n");
        return 79;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "print 1\nimport \"module.sep\" as module\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E702") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Late import") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Imports must appear before other top-level declarations and statements.") != 0 ||
        typed_diagnostic->errors[0].line_number != 2 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "late import diagnostic details missing\n");
        return 80;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main\nimport \"module.sep\" as module\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E703") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Nested import") != 0 ||
        strcmp(typed_diagnostic->errors[0].description, "Imports are allowed only at top level.") != 0 ||
        typed_diagnostic->errors[0].line_number != 2 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "nested import diagnostic details missing\n");
        return 81;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "SEP:main\nhttp_route GET \"/\" :route\nend_http_route:route\nEND_SEP:main\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E890") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Nested HTTP route") != 0 ||
        strcmp(typed_diagnostic->errors[0].description, "HTTP routes may only be declared at top level.") != 0 ||
        typed_diagnostic->errors[0].line_number != 2 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "nested HTTP route diagnostic details missing\n");
        return 82;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "http_route get \"/\" :route\nend_http_route:route\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E891") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Invalid route method") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Route method must be an uppercase supported HTTP method.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "get") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 12) {
        fprintf(stderr, "invalid route method diagnostic details missing\n");
        return 83;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "http_route GET \"users\" :route\nend_http_route:route\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E892") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Invalid route path") != 0 ||
        strcmp(typed_diagnostic->errors[0].description,
               "Route path must start with '/' and exclude query/fragment.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "users") != 0 ||
        typed_diagnostic->errors[0].line_number != 1 || typed_diagnostic->errors[0].column_number != 16) {
        fprintf(stderr, "invalid route path diagnostic details missing\n");
        return 84;
    }
    separan_result_free(typed_diagnostic);
    *typed_diagnostic = separan_validate_source(
        "http_route GET \"/\" :first\nend_http_route:first\n"
        "http_route GET \"/\" :second\nend_http_route:second\n");
    if (typed_diagnostic->ok || strcmp(typed_diagnostic->errors[0].code, "E896") != 0 ||
        strcmp(typed_diagnostic->errors[0].category, "Duplicate HTTP route") != 0 ||
        strcmp(typed_diagnostic->errors[0].description, "HTTP method and path must be unique.") != 0 ||
        strcmp(typed_diagnostic->errors[0].actual, "GET /") != 0 ||
        typed_diagnostic->errors[0].line_number != 3 || typed_diagnostic->errors[0].column_number != 1) {
        fprintf(stderr, "duplicate HTTP route diagnostic details missing\n");
        return 85;
    }
    separan_result missing_parameter_parenthesis = separan_validate_source(
        "SEP:main(value\nEND_SEP:main\n");
    if (missing_parameter_parenthesis.ok || strcmp(missing_parameter_parenthesis.errors[0].code, "E100") != 0 ||
        strcmp(missing_parameter_parenthesis.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_parameter_parenthesis.errors[0].description, "Expected ')' after parameters.") != 0 ||
        strcmp(missing_parameter_parenthesis.errors[0].actual, "\n") != 0 ||
        missing_parameter_parenthesis.errors[0].line_number != 1 ||
        missing_parameter_parenthesis.errors[0].column_number != 15) {
        fprintf(stderr, "missing function parameter delimiter diagnostic details missing\n");
        return 40;
    }
    separan_result missing_for_in = separan_validate_source(
        "SEP:main\nfor item values :loop\nendfor:loop\nEND_SEP:main\n");
    if (missing_for_in.ok || strcmp(missing_for_in.errors[0].code, "E100") != 0 ||
        strcmp(missing_for_in.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_for_in.errors[0].description, "Expected 'in' after loop variable.") != 0 ||
        strcmp(missing_for_in.errors[0].actual, "values") != 0 ||
        missing_for_in.errors[0].line_number != 2 || missing_for_in.errors[0].column_number != 10) {
        fprintf(stderr, "missing for-in separator diagnostic details missing\n");
        return 41;
    }
    separan_result missing_for_label_colon = separan_validate_source(
        "SEP:main\nfor item in [1] loop\nendfor:loop\nEND_SEP:main\n");
    if (missing_for_label_colon.ok || strcmp(missing_for_label_colon.errors[0].code, "E100") != 0 ||
        strcmp(missing_for_label_colon.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_for_label_colon.errors[0].description, "Expected :label after for expression.") != 0 ||
        strcmp(missing_for_label_colon.errors[0].actual, "loop") != 0 ||
        missing_for_label_colon.errors[0].line_number != 2 ||
        missing_for_label_colon.errors[0].column_number != 17) {
        fprintf(stderr, "missing for label colon diagnostic details missing\n");
        return 43;
    }
    separan_result missing_if_label_colon = separan_validate_source(
        "SEP:main\nif true active\nendif:active\nEND_SEP:main\n");
    if (missing_if_label_colon.ok || strcmp(missing_if_label_colon.errors[0].code, "E100") != 0 ||
        strcmp(missing_if_label_colon.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_if_label_colon.errors[0].description, "Expected :label after if expression.") != 0 ||
        strcmp(missing_if_label_colon.errors[0].actual, "active") != 0 ||
        missing_if_label_colon.errors[0].line_number != 2 || missing_if_label_colon.errors[0].column_number != 9) {
        fprintf(stderr, "missing if label colon diagnostic details missing\n");
        return 44;
    }
    separan_result missing_while_label_colon = separan_validate_source(
        "SEP:main\nwhile true active\nendwhile:active\nEND_SEP:main\n");
    if (missing_while_label_colon.ok || strcmp(missing_while_label_colon.errors[0].code, "E100") != 0 ||
        strcmp(missing_while_label_colon.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_while_label_colon.errors[0].description, "Expected :label after while expression.") != 0 ||
        strcmp(missing_while_label_colon.errors[0].actual, "active") != 0 ||
        missing_while_label_colon.errors[0].line_number != 2 || missing_while_label_colon.errors[0].column_number != 12) {
        fprintf(stderr, "missing while label colon diagnostic details missing\n");
        return 45;
    }
    separan_result function_trailing_token = separan_validate_source(
        "SEP:main() print 1\nEND_SEP:main\n");
    if (function_trailing_token.ok || strcmp(function_trailing_token.errors[0].code, "E100") != 0 ||
        strcmp(function_trailing_token.errors[0].category, "Unexpected token") != 0 ||
        strcmp(function_trailing_token.errors[0].description, "Statements must end at the end of the line.") != 0 ||
        strcmp(function_trailing_token.errors[0].actual, "print") != 0 ||
        function_trailing_token.errors[0].line_number != 1 ||
        function_trailing_token.errors[0].column_number != 12) {
        fprintf(stderr, "function trailing token diagnostic details missing\n");
        return 42;
    }
    separan_result missing_block_closer_colon = separan_validate_source("SEP:main\nEND_SEP main\n");
    if (missing_block_closer_colon.ok || strcmp(missing_block_closer_colon.errors[0].code, "E100") != 0 ||
        strcmp(missing_block_closer_colon.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_block_closer_colon.errors[0].description, "Expected ':' in block closer.") != 0 ||
        strcmp(missing_block_closer_colon.errors[0].actual, "main") != 0 ||
        missing_block_closer_colon.errors[0].line_number != 2 ||
        missing_block_closer_colon.errors[0].column_number != 9) {
        fprintf(stderr, "missing block closer colon diagnostic details missing\n");
        return 47;
    }
    separan_result missing_object_colon = separan_validate_source("object user\nend_object:user\n");
    if (missing_object_colon.ok || strcmp(missing_object_colon.errors[0].code, "E100") != 0 ||
        strcmp(missing_object_colon.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_object_colon.errors[0].description, "Expected ':' after object.") != 0 ||
        strcmp(missing_object_colon.errors[0].actual, "user") != 0 ||
        missing_object_colon.errors[0].line_number != 1 || missing_object_colon.errors[0].column_number != 8) {
        fprintf(stderr, "missing object colon diagnostic details missing\n");
        return 48;
    }
    separan_result indexed_expression_trailing_token = separan_validate_source(
        "SEP:main\nvalues = [1]\nvalues[0] 2\nEND_SEP:main\n");
    if (indexed_expression_trailing_token.ok || strcmp(indexed_expression_trailing_token.errors[0].code, "E100") != 0 ||
        strcmp(indexed_expression_trailing_token.errors[0].category, "Unexpected token") != 0 ||
        strcmp(indexed_expression_trailing_token.errors[0].description, "Statements must end at the end of the line.") != 0 ||
        strcmp(indexed_expression_trailing_token.errors[0].actual, "2") != 0 ||
        indexed_expression_trailing_token.errors[0].line_number != 3 ||
        indexed_expression_trailing_token.errors[0].column_number != 11) {
        fprintf(stderr, "indexed expression trailing token diagnostic details missing\n");
        return 49;
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
    separan_result missing_else_colon = separan_validate_source(
        "SEP:main\nif true :active\nelse active\nendif:active\nEND_SEP:main\n");
    if (missing_else_colon.ok || strcmp(missing_else_colon.errors[0].code, "E100") != 0 ||
        strcmp(missing_else_colon.errors[0].category, "Syntax error") != 0 ||
        strcmp(missing_else_colon.errors[0].description, "Expected ':' after else.") != 0 ||
        strcmp(missing_else_colon.errors[0].actual, "active") != 0 ||
        missing_else_colon.errors[0].line_number != 3 || missing_else_colon.errors[0].column_number != 6) {
        fprintf(stderr, "missing else colon diagnostic details missing\n");
        return 46;
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
    separan_result_free(&duplicate_parameter);
    separan_result_free(duplicate_object_field);
    free(duplicate_object_field);
    separan_result_free(argument_diagnostic);
    free(argument_diagnostic);
    separan_result_free(try_diagnostic);
    free(try_diagnostic);
    separan_result_free(typed_diagnostic);
    free(typed_diagnostic);
    separan_result_free(&missing_parameter_parenthesis);
    separan_result_free(&missing_for_in);
    separan_result_free(&missing_for_label_colon);
    separan_result_free(&missing_if_label_colon);
    separan_result_free(&missing_while_label_colon);
    separan_result_free(&function_trailing_token);
    separan_result_free(&missing_block_closer_colon);
    separan_result_free(&missing_object_colon);
    separan_result_free(&indexed_expression_trailing_token);
    separan_result_free(&missing_function_closer);
    separan_result_free(&missing_open_label);
    separan_result_free(&missing_else_colon);
    separan_result_free(&missing_else_label);
    separan_result_free(&missing_import_alias);
    separan_result_free(&missing_list_name);
    separan_result_free(&valid_path);
    separan_result_free(&legacy_open);
    separan_result_free(&legacy_close);
    return 0;
}
