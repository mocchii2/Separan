#ifndef SEPARAN_RUNTIME_H
#define SEPARAN_RUNTIME_H

#include <stddef.h>
#include <stdio.h>

/* Database adapters exchange UTF-8 JSON with the runtime. Return zero for
   success, or 1..7 for driver, connection, authentication, query, constraint,
   timeout, or transaction errors respectively. The connect request is
   an object containing db_connect's named arguments. Calls return a JSON value:
   rows for query operations, a scalar for db_scalar/db_execute, and the documented
   metadata shapes for metadata operations. Returned strings use release_string. */
typedef struct {
    void *context;
    int (*connect)(void *context, const char *request_json, void **connection,
                   char **error_message);
    int (*call)(void *context, void *connection, const char *operation,
                const char *request_json, char **result_json, char **error_message);
    void (*close)(void *context, void *connection);
    void (*release_string)(void *context, char *value);
} separan_database_adapter;

/* Process adapters receive an operation name and UTF-8 JSON request. Successful
   exec operations return an object with exit_code, stdout, stderr, timed_out,
   duration (milliseconds), command, and hexadecimal stdout_bytes/stderr_bytes;
   command_exists returns a JSON boolean. Status values 1..6 map to E800..E805;
   8 and 9 map to E808 (nonzero exit) and E809 (timeout). */
typedef struct {
    void *context;
    int (*call)(void *context, const char *operation, const char *request_json,
                char **result_json, char **error_message);
    void (*release_string)(void *context, char *value);
} separan_process_adapter;

/* Capability-gated host APIs (HTTP, mail, authentication, cookies, embedded
   hardware, and networking) share this transport-neutral JSON boundary. The
   request contains positional `arguments` and a `named` object. On failure the
   adapter supplies a stable Separan E-code and a diagnostic message. */
typedef struct {
    void *context;
    int (*call)(void *context, const char *operation, const char *request_json,
                char **result_json, char **error_code, char **error_message);
    void (*release_string)(void *context, char *value);
} separan_host_adapter;

typedef struct {
    const char *root;
    int read_files;
    int write_files;
    int discover_paths;
    int import_modules;
    int read_environment;
    int write_environment;
    const char *script_path;
    const char *const *command_arguments;
    size_t command_argument_count;
    const separan_database_adapter *database;
    const separan_process_adapter *process;
    const separan_host_adapter *host;
} separan_runtime_options;

#define SEPARAN_RUNTIME_DIAGNOSTIC_LEN 256
typedef struct {
   size_t line_number;
   size_t column_number;
   size_t related_line_number;
   size_t related_column_number;
   char category[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
   char description[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
   char expected[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
   char actual[SEPARAN_RUNTIME_DIAGNOSTIC_LEN];
} separan_runtime_diagnostic;

/* A parsed runtime can be retained and invoked repeatedly. Arguments are a
   UTF-8 JSON array. The returned JSON string is allocated by the runtime API
   and must be released with separan_runtime_release_string(). VOID results are
   encoded as JSON null. */
typedef struct separan_runtime separan_runtime;
int separan_runtime_create(const char *source, const separan_runtime_options *options,
                           FILE *output, FILE *errors, separan_runtime **runtime);
int separan_runtime_invoke_json(separan_runtime *runtime, const char *function_name,
                                const char *arguments_json, char **result_json);
/* Dispatch one request through http_route declarations. request_json contains
   method, path, and optional query, headers, and body fields. */
int separan_runtime_dispatch_http_json(separan_runtime *runtime, const char *request_json,
                                       char **response_json);
/* Copy the last runtime failure detail after invoke or dispatch. */
void separan_runtime_get_diagnostic(const separan_runtime *runtime,
                                   separan_runtime_diagnostic *diagnostic);
void separan_runtime_release_string(char *value);
void separan_runtime_destroy(separan_runtime *runtime);

/* Parse and validate without executing top-level statements or main. */
int separan_check_source(const char *source, FILE *errors);
int separan_check_path(const char *path, FILE *errors);
/* Structured validation detail bridge used by separan_validate_* APIs. */
int separan_check_source_detailed(const char *source, FILE *errors,
                                  separan_runtime_diagnostic *diagnostic);
int separan_check_path_detailed(const char *path, FILE *errors,
                                separan_runtime_diagnostic *diagnostic);
/* Inspect named blocks without executing source. The allocated JSON result must
   be released with separan_runtime_release_string(). */
int separan_inspect_path_json(const char *path, char **result_json, FILE *errors);
int separan_inspect_tag_path_json(const char *path, const char *tag,
                                  char **result_json, FILE *errors);
int separan_verify_tag_scope_json(const char *before_path, const char *after_path,
                                  const char *tag, char **result_json,
                                  int *passed, FILE *errors);

/* Parse and execute the supported core language. Returns zero on success. */
int separan_run_source(const char *source, FILE *output, FILE *errors);
int separan_run_source_with_options(const char *source, const separan_runtime_options *options,
                                    FILE *output, FILE *errors);
int separan_run_path(const char *path, FILE *output, FILE *errors);
int separan_run_path_with_arguments(const char *path, const char *const *arguments,
                                    size_t argument_count, FILE *output, FILE *errors);

#endif
