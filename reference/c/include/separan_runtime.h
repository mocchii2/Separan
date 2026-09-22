#ifndef SEPARAN_RUNTIME_H
#define SEPARAN_RUNTIME_H

#include <stdio.h>

typedef struct {
    const char *root;
    int read_files;
    int write_files;
    int discover_paths;
} separan_runtime_options;

/* Parse and execute the supported core language. Returns zero on success. */
int separan_run_source(const char *source, FILE *output, FILE *errors);
int separan_run_source_with_options(const char *source, const separan_runtime_options *options,
                                    FILE *output, FILE *errors);
int separan_run_path(const char *path, FILE *output, FILE *errors);

#endif
