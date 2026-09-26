#include "separan_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *read_source(const char *path) {
    FILE *file = fopen(path, "rb");
    if (!file) return NULL;
    if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
    long size = ftell(file);
    if (size < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
    char *source = malloc((size_t)size + 1);
    if (!source) { fclose(file); return NULL; }
    size_t count = fread(source, 1, (size_t)size, file);
    fclose(file);
    if (count != (size_t)size) { free(source); return NULL; }
    source[count] = '\0';
    return source;
}

static void print_help(const char *program) {
    printf("Separan Gateway Worker\n");
    printf("Usage: %s --source <app.sep> [--stdio]\n", program);
    printf("\n");
    printf("Read one HTTP request JSON object per stdin line and write one response JSON object per stdout line.\n");
    printf("The stdio transport is the development and adapter boundary for future FastCGI/socket listeners.\n");
}

int main(int argc, char **argv) {
    const char *source_path = NULL;
    for (int index = 1; index < argc; index++) {
        if (!strcmp(argv[index], "-help") || !strcmp(argv[index], "--help")) {
            print_help(argv[0]);
            return 0;
        }
        if (!strcmp(argv[index], "--source") && index + 1 < argc) {
            source_path = argv[++index];
            continue;
        }
        if (!strcmp(argv[index], "--stdio")) continue;
        fprintf(stderr, "separan-gw: unknown or incomplete option '%s'\n", argv[index]);
        return 2;
    }
    if (!source_path) {
        fprintf(stderr, "separan-gw: --source <app.sep> is required\n");
        return 2;
    }

    char *source = read_source(source_path);
    if (!source) {
        fprintf(stderr, "separan-gw: cannot read %s\n", source_path);
        return 1;
    }
    FILE *errors = stderr;
    separan_runtime_options options = {
        .root = ".", .read_files = 1, .write_files = 0, .discover_paths = 0,
        .import_modules = 1, .read_environment = 1, .write_environment = 0,
        .script_path = source_path,
    };
    separan_runtime *runtime = NULL;
    if (separan_runtime_create(source, &options, stdout, errors, &runtime)) {
        free(source);
        return 1;
    }
    free(source);

    const size_t request_capacity = 1024 * 1024;
    char *request = malloc(request_capacity);
    if (!request) {
        separan_runtime_destroy(runtime);
        return 1;
    }
    while (fgets(request, (int)request_capacity, stdin)) {
        size_t length = strlen(request);
        while (length && (request[length - 1] == '\n' || request[length - 1] == '\r')) request[--length] = '\0';
        if (!length) continue;
        char *response = NULL;
        if (separan_runtime_dispatch_http_json(runtime, request, &response)) {
            separan_runtime_diagnostic diagnostic;
            separan_runtime_get_diagnostic(runtime, &diagnostic);
            fprintf(stderr, "separan-gw: %s at line %zu, column %zu\n",
                    diagnostic.description[0] ? diagnostic.description : "request failed",
                    diagnostic.line_number, diagnostic.column_number);
            free(response);
            free(request);
            separan_runtime_destroy(runtime);
            return 1;
        }
        if (!response || puts(response) == EOF) {
            free(response);
            free(request);
            separan_runtime_destroy(runtime);
            return 1;
        }
        free(response);
    }
    int input_error = ferror(stdin);
    free(request);
    separan_runtime_destroy(runtime);
    return input_error ? 1 : 0;
}
