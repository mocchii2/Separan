#ifndef SEPARAN_CORE_H
#define SEPARAN_CORE_H

#include <stddef.h>

#define SEPARAN_MAX_ERRORS 16
#define SEPARAN_CODE_LEN 16
#define SEPARAN_MESSAGE_LEN 256

typedef struct {
    int line_number;
    char code[SEPARAN_CODE_LEN];
    char title[SEPARAN_MESSAGE_LEN];
    char expected[SEPARAN_MESSAGE_LEN];
    char actual[SEPARAN_MESSAGE_LEN];
} separan_error;

typedef struct {
    int ok;
    size_t error_count;
    separan_error errors[SEPARAN_MAX_ERRORS];
} separan_result;

int separan_analyze_source(const char *source);
int separan_analyze_path(const char *path);
separan_result separan_validate_source(const char *source);
separan_result separan_validate_path(const char *path);
void separan_reset_result(separan_result *result);
void separan_result_free(separan_result *result);

#endif
