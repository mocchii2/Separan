#include "separan_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif

static double now_seconds(void) {
#ifdef _WIN32
    static LARGE_INTEGER frequency;
    static int initialized;
    LARGE_INTEGER counter;
    if (!initialized) { QueryPerformanceFrequency(&frequency); initialized = 1; }
    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart / (double)frequency.QuadPart;
#else
    struct timespec timestamp;
    clock_gettime(CLOCK_MONOTONIC, &timestamp);
    return (double)timestamp.tv_sec + (double)timestamp.tv_nsec / 1000000000.0;
#endif
}

static int run_case(const char *name, const char *source, int iterations) {
    separan_runtime_options options = {.root = ".", .read_files = 0,
                                       .write_files = 0, .discover_paths = 0};
    FILE *output = tmpfile(), *errors = tmpfile();
    separan_runtime *runtime = NULL;
    char *response = NULL;
    const char *request = "{\"method\":\"GET\",\"path\":\"/user/42\"}";
    if (!output || !errors || separan_runtime_create(source, &options, output, errors, &runtime)) {
        if (output) fclose(output);
        if (errors) fclose(errors);
        return 1;
    }
    double start = now_seconds();
    for (int iteration = 0; iteration < iterations; iteration++) {
        if (separan_runtime_dispatch_http_json(runtime, request, &response)) {
            separan_runtime_destroy(runtime); fclose(output); fclose(errors); return 1;
        }
        separan_runtime_release_string(response); response = NULL;
    }
        double end = now_seconds();
        printf("%s: %.3f ms/request (%d requests)\n", name,
            (end - start) * 1000.0 / (double)iterations, iterations);
    separan_runtime_destroy(runtime);
    fclose(output); fclose(errors);
    return 0;
}

int main(int argc, char **argv) {
    int iterations = argc > 1 ? atoi(argv[1]) : 10000;
    if (iterations < 1) iterations = 1;
    const char *compiled_source =
        "http_route GET \"/user/:id\" :user\n"
        "return_http(status = 200, body = request_method() + \" \" + request_param(\"id\"))\n"
        "end_http_route:user\n";
    const char *fallback_source =
        "http_route GET \"/user/:id\" :user\n"
        "if true :guard\n"
        "value = request_method() + \" \" + request_param(\"id\")\n"
        "endif:guard\n"
        "return_http(status = 200, body = value)\n"
        "end_http_route:user\n";
    if (run_case("bytecode", compiled_source, iterations) ||
        run_case("ast-fallback", fallback_source, iterations)) return 1;
    return 0;
}
