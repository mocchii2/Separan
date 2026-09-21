#include "separan_core.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void print_help(const char *program_name) {
    printf("Separan native core\n");
    printf("Usage: %s <source.sep>\n", program_name);
    printf("       %s -help\n", program_name);
    printf("\n");
    printf("Validate the structural block labels and syntax in a Separan source file.\n");
}

int main(int argc, char **argv) {
    if (argc == 2 && (strcmp(argv[1], "-help") == 0 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "/?") == 0)) {
        print_help(argv[0]);
        return 0;
    }

    if (argc != 2) {
        fprintf(stderr, "Usage: %s <source.sep>\n", argv[0]);
        return 2;
    }

    int result = separan_analyze_path(argv[1]);
    if (result == 0) {
        printf("Separan native core: OK\n");
    }
    return result;
}
