#include "separan_runtime.h"

#include <stdio.h>
#include <string.h>

int main(void) {
    separan_runtime_options restricted = {".", 0, 0, 0};
    FILE *output = tmpfile(), *errors = tmpfile();
    if (!output || !errors) return 1;
    if (separan_run_source_with_options("print 2 + 3\n", &restricted, output, errors)) return 2;
    rewind(output);
    char line[128];
    if (!fgets(line, sizeof(line), output) || strcmp(line, "5\n")) return 3;
    if (!separan_run_source_with_options("print read_text(\"x.txt\")\n", &restricted, output, errors)) return 4;
    rewind(errors);
    if (!fgets(line, sizeof(line), errors) || !strstr(line, "E720")) return 5;
    fclose(output); fclose(errors);
    puts("runtime_api: ok");
    return 0;
}
