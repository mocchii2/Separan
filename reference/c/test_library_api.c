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

    separan_result duplicate = separan_validate_source(
        "SEP:main\nif true :same\nwhile true :same\nendwhile:same\nendif:same\nEND_SEP:main\n");
    if (duplicate.ok || duplicate.error_count == 0U ||
        strcmp(duplicate.errors[0].code, "E109") != 0) {
        fprintf(stderr, "duplicate label did not return a structured error\n");
        return 4;
    }

    printf("library_api: ok\n");
    separan_result_free(&ok);
    separan_result_free(&bad);
    separan_result_free(&duplicate);
    return 0;
}
