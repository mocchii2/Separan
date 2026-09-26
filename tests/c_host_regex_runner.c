#include "separan_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *copy_text(const char *text) {
    size_t length = strlen(text);
    char *copy = malloc(length + 1);
    if (copy) memcpy(copy, text, length + 1);
    return copy;
}

static int regex_host_call(void *context, const char *operation, const char *request,
                           char **result, char **error_code, char **error_message) {
    (void)context;
    (void)request;
    (void)error_code;
    (void)error_message;
    if (strcmp(operation, "regex_find")) return 1;
    *result = copy_text("{\"text\":\"a\",\"start\":0,\"end\":1,\"groups\":[\"a\"]}");
    return *result ? 0 : 1;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *source_file = fopen(argv[1], "rb");
    if (!source_file || fseek(source_file, 0, SEEK_END)) return 2;
    long length = ftell(source_file);
    if (length < 0 || fseek(source_file, 0, SEEK_SET)) {
        fclose(source_file);
        return 2;
    }
    char *source = malloc((size_t)length + 1);
    if (!source) {
        fclose(source_file);
        return 2;
    }
    size_t read_length = fread(source, 1, (size_t)length, source_file);
    fclose(source_file);
    source[read_length] = '\0';
    separan_host_adapter host = {.call = regex_host_call};
    separan_runtime_options options = {.root = ".", .host = &host};
    int result = separan_run_source_with_options(source, &options, stdout, stderr);
    free(source);
    return result;
}
