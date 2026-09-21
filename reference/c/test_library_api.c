#include "separan_core.h"

#include <stdio.h>

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

    printf("library_api: ok\n");
    separan_result_free(&ok);
    separan_result_free(&bad);
    return 0;
}
