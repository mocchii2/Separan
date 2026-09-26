#include "separan_runtime.h"
#include "separan_gw_transport.h"

#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <unistd.h>
#endif

static char **gateway_argv;

int separan_gw_reload_process(void) {
#ifdef _WIN32
    fputs("separan-gw: in-place reload is unavailable on Windows\n", stderr);
    return 1;
#else
    execv(gateway_argv[0], gateway_argv);
    perror("separan-gw: exec for reload");
    return 1;
#endif
}

static char *trim(char *text) {
    while (*text == ' ' || *text == '\t') text++;
    size_t length = strlen(text);
    while (length && (text[length - 1] == ' ' || text[length - 1] == '\t' ||
                      text[length - 1] == '\r' || text[length - 1] == '\n')) text[--length] = '\0';
    return text;
}

static int set_listener(const char *value, char *transport, size_t transport_capacity,
                        char *endpoint, size_t endpoint_capacity) {
    const char *prefix = NULL;
    const char *listener_transport = NULL;
    if (!strncmp(value, "unix:", 5)) { prefix = value + 5; listener_transport = "fastcgi-unix"; }
    else if (!strncmp(value, "tcp:", 4)) { prefix = value + 4; listener_transport = "fastcgi-tcp"; }
    else if (!strncmp(value, "pipe:", 5)) { prefix = value + 5; listener_transport = "fastcgi-pipe"; }
    if (!prefix || !*prefix || strlen(prefix) >= endpoint_capacity || strlen(listener_transport) >= transport_capacity) return 0;
    snprintf(endpoint, endpoint_capacity, "%s", prefix);
    snprintf(transport, transport_capacity, "%s", listener_transport);
    return 1;
}

static int transport_needs_listener(const char *transport) {
    return !strcmp(transport, "fastcgi-unix") || !strcmp(transport, "fastcgi-tcp") || !strcmp(transport, "fastcgi-pipe");
}

static int parse_count(const char *text, size_t *result) {
    if (!*text || *text == '-') return 0;
    errno = 0;
    char *end = NULL;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno || end == text || *end || !value || value > SIZE_MAX) return 0;
    *result = (size_t)value;
    return 1;
}

static int parse_memory_limit(const char *text, size_t *result) {
    if (!*text || *text == '-') return 0;
    errno = 0;
    char *end = NULL;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno || end == text || !value) return 0;
    unsigned long long multiplier = 1;
    if (*end) {
        char suffix = (char)toupper((unsigned char)*end++);
        if (suffix == 'K') multiplier = 1024ULL;
        else if (suffix == 'M') multiplier = 1024ULL * 1024ULL;
        else if (suffix == 'G') multiplier = 1024ULL * 1024ULL * 1024ULL;
        else return 0;
        if (*end == 'B' || *end == 'b') end++;
        if (*end) return 0;
    }
    if (value > SIZE_MAX / multiplier) return 0;
    *result = (size_t)(value * multiplier);
    return 1;
}

static int parse_duration_ms(const char *text, unsigned *result) {
    if (!*text || *text == '-') return 0;
    errno = 0;
    char *end = NULL;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno || end == text) return 0;
    unsigned long long multiplier;
    if (!strcmp(end, "ms")) multiplier = 1;
    else if (!strcmp(end, "s")) multiplier = 1000;
    else if (!strcmp(end, "m")) multiplier = 60000;
    else return 0;
    if (value > UINT_MAX / multiplier) return 0;
    *result = (unsigned)(value * multiplier);
    return 1;
}

static int read_config(const char *path, char *source_path, size_t source_capacity,
                       char *transport, size_t transport_capacity,
                       char *socket_path, size_t socket_capacity,
                       separan_gw_supervisor_options *supervisor) {
    FILE *file = fopen(path, "rb");
    if (!file) { fprintf(stderr, "separan-gw: cannot read config %s\n", path); return 0; }
    char line[4096];
    unsigned line_number = 0;
    int ok = 1;
    while (fgets(line, sizeof(line), file)) {
        line_number++;
        size_t raw_length = strlen(line);
        if (raw_length && line[raw_length - 1] != '\n' && !feof(file)) {
            fprintf(stderr, "separan-gw: %s:%u: config line exceeds %zu bytes\n", path, line_number, sizeof(line) - 1);
            ok = 0; break;
        }
        char *entry = trim(line);
        if (!*entry || *entry == '#') continue;
        char *equals = strchr(entry, '=');
        if (!equals) {
            fprintf(stderr, "separan-gw: %s:%u: expected key = value\n", path, line_number);
            ok = 0; break;
        }
        *equals = '\0';
        char *key = trim(entry);
        char *value = trim(equals + 1);
        size_t value_length = strlen(value);
        if (value_length >= 2 && ((value[0] == '"' && value[value_length - 1] == '"') ||
                                  (value[0] == '\'' && value[value_length - 1] == '\''))) {
            value[value_length - 1] = '\0'; value++;
        }
        if (!strcmp(key, "source")) {
            if (!*value || strlen(value) >= source_capacity) {
                fprintf(stderr, "separan-gw: %s:%u: invalid source path\n", path, line_number);
                ok = 0; break;
            }
            snprintf(source_path, source_capacity, "%s", value);
        } else if (!strcmp(key, "transport")) {
            if (strcmp(value, "stdio") && strcmp(value, "fastcgi-stdio") && strcmp(value, "fastcgi-unix") &&
                strcmp(value, "fastcgi-tcp") && strcmp(value, "fastcgi-pipe")) {
                fprintf(stderr, "separan-gw: %s:%u: unsupported transport '%s'\n", path, line_number, value);
                ok = 0; break;
            }
            if (strlen(value) >= transport_capacity) { ok = 0; break; }
            snprintf(transport, transport_capacity, "%s", value);
        } else if (!strcmp(key, "listen")) {
            if (!set_listener(value, transport, transport_capacity, socket_path, socket_capacity)) {
                fprintf(stderr, "separan-gw: %s:%u: listen must use unix:<path>, tcp:<host>:<port>, or pipe:<name>\n", path, line_number);
                ok = 0; break;
            }
        } else if (!strcmp(key, "workers")) {
            size_t workers = 0;
            if (!parse_count(value, &workers) || workers > 256) {
                fprintf(stderr, "separan-gw: %s:%u: workers must be between 1 and 256\n", path, line_number);
                ok = 0; break;
            }
            supervisor->workers = (unsigned)workers; supervisor->enabled = 1;
        } else if (!strcmp(key, "max_memory")) {
            if (!parse_memory_limit(value, &supervisor->max_memory_bytes)) {
                fprintf(stderr, "separan-gw: %s:%u: max_memory must be a positive byte size (K, M, or G suffix allowed)\n", path, line_number);
                ok = 0; break;
            }
            supervisor->enabled = 1;
        } else if (!strcmp(key, "max_requests")) {
            if (!parse_count(value, &supervisor->max_requests)) {
                fprintf(stderr, "separan-gw: %s:%u: max_requests must be a positive integer\n", path, line_number);
                ok = 0; break;
            }
            supervisor->enabled = 1;
        } else if (!strcmp(key, "restart_grace")) {
            if (!parse_duration_ms(value, &supervisor->restart_grace_ms)) {
                fprintf(stderr, "separan-gw: %s:%u: restart_grace must use ms, s, or m units\n", path, line_number);
                ok = 0; break;
            }
            supervisor->enabled = 1;
        } else if (!strcmp(key, "restart_backoff")) {
            if (!parse_duration_ms(value, &supervisor->restart_backoff_ms)) {
                fprintf(stderr, "separan-gw: %s:%u: restart_backoff must use ms, s, or m units\n", path, line_number);
                ok = 0; break;
            }
            supervisor->enabled = 1;
        } else {
            fprintf(stderr, "separan-gw: %s:%u: unsupported setting '%s'\n", path, line_number, key);
            ok = 0; break;
        }
    }
    if (ferror(file)) { fprintf(stderr, "separan-gw: error reading config %s\n", path); ok = 0; }
    if (ok && transport_needs_listener(transport) && !socket_path[0]) {
        fprintf(stderr, "separan-gw: %s: %s requires a listen setting\n", path, transport);
        ok = 0;
    }
    if (ok && socket_path[0] && !transport_needs_listener(transport)) {
        fprintf(stderr, "separan-gw: %s: listen requires a FastCGI listener transport\n", path);
        ok = 0;
    }
    if (ok && supervisor->enabled && !transport_needs_listener(transport)) {
        fprintf(stderr, "separan-gw: %s: supervisor settings require a FastCGI listener\n", path);
        ok = 0;
    }
    fclose(file); return ok;
}

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
    printf("Usage: %s --source <app.sep> [--stdio|--fastcgi-stdio|--listen unix:<path>|tcp:<host>:<port>|pipe:<name>]\n", program);
    printf("       %s --source <app.sep> --fastcgi-stdio\n", program);
    printf("       %s --config <separan-gw.conf> [--service]\n", program);
    printf("\n");
    printf("Config supports source, transport, listeners, workers, max_memory, max_requests, restart_grace, and restart_backoff.\n");
    printf("stdio reads JSON lines; FastCGI transports speak FastCGI v1 records.\n");
    printf("Listeners currently run single-worker; process supervision is not implemented yet.\n");
}

int main(int argc, char **argv) {
    gateway_argv = argv;
    char source_path[4096] = {0};
    char config_path[4096] = {0};
    char transport[32] = "stdio";
    char socket_path[4096] = {0};
    char inherited_listener_pipe[256] = {0};
    separan_gw_supervisor_options supervisor = {1, 0, 0, 5000, 1000, 0};
    int internal_worker = 0;
    int run_as_service = 0;
    for (int index = 1; index < argc; index++) {
        if (!strcmp(argv[index], "-help") || !strcmp(argv[index], "--help")) {
            print_help(argv[0]);
            return 0;
        }
        if (!strcmp(argv[index], "--config") && index + 1 < argc) {
            snprintf(config_path, sizeof(config_path), "%s", argv[++index]);
            if (!read_config(config_path, source_path, sizeof(source_path), transport, sizeof(transport), socket_path, sizeof(socket_path), &supervisor)) return 2;
            continue;
        }
        if (!strcmp(argv[index], "--internal-worker")) { internal_worker = 1; continue; }
        if (!strcmp(argv[index], "--service")) { run_as_service = 1; continue; }
        if (!strcmp(argv[index], "--inherited-listener-pipe") && index + 1 < argc) {
            snprintf(inherited_listener_pipe, sizeof(inherited_listener_pipe), "%s", argv[++index]);
            continue;
        }
        if (!strcmp(argv[index], "--source") && index + 1 < argc) {
            snprintf(source_path, sizeof(source_path), "%s", argv[++index]);
            continue;
        }
        if (!strcmp(argv[index], "--stdio")) continue;
        if (!strcmp(argv[index], "--fastcgi-stdio")) { snprintf(transport, sizeof(transport), "fastcgi-stdio"); continue; }
        if (!strcmp(argv[index], "--listen") && index + 1 < argc) {
            if (!set_listener(argv[++index], transport, sizeof(transport), socket_path, sizeof(socket_path))) {
                fprintf(stderr, "separan-gw: --listen requires unix:<path>, tcp:<host>:<port>, or pipe:<name>\n"); return 2;
            }
            continue;
        }
        fprintf(stderr, "separan-gw: unknown or incomplete option '%s'\n", argv[index]);
        return 2;
    }
    if (!source_path[0]) {
        fprintf(stderr, "separan-gw: --source <app.sep> or config source = <path> is required\n");
        return 2;
    }
#ifdef _WIN32
    if (!internal_worker && (supervisor.enabled || run_as_service)) {
        if ((strcmp(transport, "fastcgi-pipe") && strcmp(transport, "fastcgi-tcp")) || !config_path[0]) {
            fprintf(stderr, "separan-gw: Windows process supervision requires a config with fastcgi-pipe or fastcgi-tcp transport\n");
            return 2;
        }
        if (run_as_service)
            return separan_gw_run_windows_service(config_path, transport, socket_path, &supervisor);
        return separan_gw_supervise_windows(config_path, transport, socket_path, &supervisor);
    }
#endif
    if (internal_worker) supervisor.enabled = 0;
    char *source = read_source(source_path);
    if (!source) {
        fprintf(stderr, "separan-gw: cannot read %s\n", source_path);
        return 1;
    }
    uintptr_t inherited_tcp_listener = 0;
    if (inherited_listener_pipe[0]) {
#ifdef _WIN32
        if (strcmp(transport, "fastcgi-tcp") ||
            separan_gw_receive_windows_tcp_socket(inherited_listener_pipe, &inherited_tcp_listener)) {
            free(source); return 1;
        }
#else
        free(source); fprintf(stderr, "separan-gw: inherited TCP listeners are Windows-only\n"); return 2;
#endif
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

    if (!strcmp(transport, "fastcgi-stdio") || transport_needs_listener(transport)) {
        int status;
        if (!strcmp(transport, "fastcgi-unix")) status = separan_gw_run_fastcgi_unix(runtime, socket_path, &supervisor);
        else if (!strcmp(transport, "fastcgi-tcp"))
            status = inherited_tcp_listener
                ? separan_gw_run_fastcgi_tcp_socket(runtime, inherited_tcp_listener, &supervisor)
                : separan_gw_run_fastcgi_tcp(runtime, socket_path, &supervisor);
        else if (!strcmp(transport, "fastcgi-pipe")) status = separan_gw_run_fastcgi_pipe(runtime, socket_path, &supervisor);
        else status = separan_gw_run_fastcgi_stdio(runtime);
        separan_runtime_destroy(runtime);
        return status;
    }

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
