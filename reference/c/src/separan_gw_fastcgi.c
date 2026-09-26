#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif

#include "separan_gw_transport.h"

#include <ctype.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <psapi.h>
#include <fcntl.h>
#include <io.h>
#else
#include <errno.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#endif

#define FCGI_VERSION_1 1
#define FCGI_BEGIN_REQUEST 1
#define FCGI_ABORT_REQUEST 2
#define FCGI_END_REQUEST 3
#define FCGI_PARAMS 4
#define FCGI_STDIN 5
#define FCGI_STDOUT 6
#define FCGI_STDERR 7
#define FCGI_GET_VALUES 9
#define FCGI_GET_VALUES_RESULT 10
#define FCGI_RESPONDER 1
#define FCGI_REQUEST_COMPLETE 0
#define FCGI_UNKNOWN_ROLE 3
#define FCGI_MAX_CONTENT 65535
#define FCGI_MAX_STREAM (16u * 1024u * 1024u)

typedef struct { unsigned char *data; size_t length, capacity; } Buffer;
typedef struct { char *name; char *value; } Param;
typedef struct { Param *items; size_t count; } Params;
typedef struct {
    void *context;
    int (*read)(void *context, unsigned char *buffer, size_t capacity);
    int (*write)(void *context, const unsigned char *buffer, size_t length);
    int (*flush)(void *context);
} FastcgiStream;
typedef struct { FILE *input; FILE *output; } FileStreamContext;
#ifdef _WIN32
typedef SOCKET GatewaySocket;
#else
typedef int GatewaySocket;
#endif
typedef struct { GatewaySocket socket; } SocketStreamContext;
typedef struct {
    size_t requests;
    size_t max_requests;
    size_t max_memory_bytes;
    volatile sig_atomic_t *stop_requested;
} WorkerLimits;
static int run_fastcgi_stream(separan_runtime *runtime, FastcgiStream *stream, WorkerLimits *worker);
static int worker_should_recycle(const WorkerLimits *worker);
static int run_socket_endpoint(separan_runtime *runtime, GatewaySocket listener,
                               const char *socket_path, const separan_gw_supervisor_options *options);

static int buffer_append(Buffer *buffer, const void *data, size_t length) {
    if (length > FCGI_MAX_STREAM || buffer->length > FCGI_MAX_STREAM - length) return 0;
    size_t required = buffer->length + length;
    if (required > buffer->capacity) {
        size_t capacity = buffer->capacity ? buffer->capacity : 256;
        while (capacity < required) {
            if (capacity > FCGI_MAX_STREAM / 2) { capacity = FCGI_MAX_STREAM; break; }
            capacity *= 2;
        }
        unsigned char *next = realloc(buffer->data, capacity);
        if (!next) return 0;
        buffer->data = next; buffer->capacity = capacity;
    }
    if (length) memcpy(buffer->data + buffer->length, data, length);
    buffer->length += length;
    return 1;
}

static int json_string(Buffer *buffer, const unsigned char *text, size_t length) {
    static const char hex[] = "0123456789abcdef";
    if (!buffer_append(buffer, "\"", 1)) return 0;
    for (size_t index = 0; index < length; index++) {
        unsigned char value = text[index];
        if (value == '"' || value == '\\') {
            unsigned char escaped[2] = {'\\', value};
            if (!buffer_append(buffer, escaped, sizeof(escaped))) return 0;
        } else if (value == '\n') { if (!buffer_append(buffer, "\\n", 2)) return 0; }
        else if (value == '\r') { if (!buffer_append(buffer, "\\r", 2)) return 0; }
        else if (value == '\t') { if (!buffer_append(buffer, "\\t", 2)) return 0; }
        else if (value < 0x20) {
            char escaped[7]; snprintf(escaped, sizeof(escaped), "\\u00%c%c", hex[value >> 4], hex[value & 15]);
            if (!buffer_append(buffer, escaped, 6)) return 0;
        } else if (!buffer_append(buffer, &value, 1)) return 0;
    }
    return buffer_append(buffer, "\"", 1);
}

static int json_member(Buffer *buffer, const char *name, const char *value, size_t value_length, int *first) {
    if ((!*first && !buffer_append(buffer, ",", 1)) || !json_string(buffer, (const unsigned char *)name, strlen(name)) ||
        !buffer_append(buffer, ":", 1) || !json_string(buffer, (const unsigned char *)value, value_length)) return 0;
    *first = 0; return 1;
}

static const char *param_value(const Params *params, const char *name) {
    for (size_t index = 0; index < params->count; index++)
        if (!strcmp(params->items[index].name, name)) return params->items[index].value;
    return NULL;
}

static void params_free(Params *params) {
    for (size_t index = 0; index < params->count; index++) { free(params->items[index].name); free(params->items[index].value); }
    free(params->items); memset(params, 0, sizeof(*params));
}

static int read_length(const unsigned char *data, size_t length, size_t *offset, size_t *value) {
    if (*offset >= length) return 0;
    unsigned char first = data[(*offset)++];
    if (!(first & 0x80)) { *value = first; return 1; }
    if (length - *offset < 3) return 0;
    *value = ((size_t)(first & 0x7f) << 24) | ((size_t)data[*offset] << 16) |
             ((size_t)data[*offset + 1] << 8) | data[*offset + 2];
    *offset += 3; return 1;
}

static int parse_params(const Buffer *encoded, Params *params) {
    size_t offset = 0;
    while (offset < encoded->length) {
        size_t name_length, value_length;
        if (!read_length(encoded->data, encoded->length, &offset, &name_length) ||
            !read_length(encoded->data, encoded->length, &offset, &value_length) ||
            name_length > encoded->length - offset || value_length > encoded->length - offset - name_length) return 0;
        char *name = malloc(name_length + 1), *value = malloc(value_length + 1);
        if (!name || !value) { free(name); free(value); return 0; }
        memcpy(name, encoded->data + offset, name_length); name[name_length] = 0; offset += name_length;
        memcpy(value, encoded->data + offset, value_length); value[value_length] = 0; offset += value_length;
        Param *next = realloc(params->items, (params->count + 1) * sizeof(*next));
        if (!next) { free(name); free(value); return 0; }
        params->items = next; params->items[params->count++] = (Param){name, value};
    }
    return 1;
}

static int hex_value(unsigned char value) {
    if (value >= '0' && value <= '9') return value - '0';
    value = (unsigned char)tolower(value);
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    return -1;
}

static char *url_decode(const char *text, size_t length) {
    char *decoded = malloc(length + 1);
    if (!decoded) return NULL;
    size_t output = 0;
    for (size_t index = 0; index < length; index++) {
        if (text[index] == '+') decoded[output++] = ' ';
        else if (text[index] == '%' && index + 2 < length) {
            int high = hex_value((unsigned char)text[index + 1]), low = hex_value((unsigned char)text[index + 2]);
            if (high < 0 || low < 0) { free(decoded); return NULL; }
            decoded[output++] = (char)((high << 4) | low); index += 2;
        } else decoded[output++] = text[index];
    }
    decoded[output] = 0; return decoded;
}

static int append_query(Buffer *json, const char *query) {
    if (!buffer_append(json, "{", 1)) return 0;
    int first = 1;
    while (query && *query) {
        const char *end = strchr(query, '&'); size_t pair_length = end ? (size_t)(end - query) : strlen(query);
        const char *equals = memchr(query, '=', pair_length); size_t key_length = equals ? (size_t)(equals - query) : pair_length;
        size_t value_length = equals ? pair_length - key_length - 1 : 0;
        char *key = url_decode(query, key_length), *value = url_decode(equals ? equals + 1 : "", value_length);
        if (!key || !value) { free(key); free(value); return 0; }
        int ok = json_member(json, key, value, strlen(value), &first); free(key); free(value);
        if (!ok) return 0;
        if (!end) break;
        query = end + 1;
    }
    return buffer_append(json, "}", 1);
}

static int request_json(const Params *params, const Buffer *body, Buffer *json) {
    const char *method = param_value(params, "REQUEST_METHOD");
    const char *path = param_value(params, "PATH_INFO");
    const char *uri = param_value(params, "REQUEST_URI");
    const char *query = param_value(params, "QUERY_STRING");
    if ((!path || !*path) && uri) {
        path = uri;
        const char *mark = strchr(uri, '?');
        if (mark) {
            static char uri_path[8192]; size_t length = (size_t)(mark - uri);
            if (length >= sizeof(uri_path)) return 0;
            memcpy(uri_path, uri, length); uri_path[length] = 0; path = uri_path;
            if (!query) query = mark + 1;
        }
    }
    if (!method || !path) return 0;
    if (!buffer_append(json, "{\"method\":", strlen("{\"method\":")) || !json_string(json, (const unsigned char *)method, strlen(method)) ||
        !buffer_append(json, ",\"path\":", strlen(",\"path\":")) || !json_string(json, (const unsigned char *)path, strlen(path)) ||
        !buffer_append(json, ",\"query\":", strlen(",\"query\":")) || !append_query(json, query) || !buffer_append(json, ",\"headers\":{", strlen(",\"headers\":{"))) return 0;
    int first = 1;
    for (size_t index = 0; index < params->count; index++) {
        const char *name = params->items[index].name;
        const char *header = NULL;
        char normalized[1024];
        if (!strncmp(name, "HTTP_", 5)) header = name + 5;
        else if (!strcmp(name, "CONTENT_TYPE") || !strcmp(name, "CONTENT_LENGTH")) header = name;
        if (!header) continue;
        size_t length = strlen(header);
        if (length >= sizeof(normalized)) return 0;
        for (size_t i = 0; i <= length; i++) normalized[i] = header[i] == '_' ? '-' : (char)tolower((unsigned char)header[i]);
        if (!json_member(json, normalized, params->items[index].value, strlen(params->items[index].value), &first)) return 0;
    }
    static const char hex[] = "0123456789abcdef";
    if (!buffer_append(json, "},\"body\":{\"$bytes\":\"", strlen("},\"body\":{\"$bytes\":\""))) return 0;
    for (size_t index = 0; index < body->length; index++) {
        char pair[2] = {hex[body->data[index] >> 4], hex[body->data[index] & 15]};
        if (!buffer_append(json, pair, 2)) return 0;
    }
    return buffer_append(json, "\"}}", 3);
}

static int read_exact(FastcgiStream *stream, unsigned char *buffer, size_t length, int allow_clean_eof) {
    size_t offset = 0;
    while (offset < length) {
        int count = stream->read(stream->context, buffer + offset, length - offset);
        if (count < 0) return -1;
        if (!count) return allow_clean_eof && !offset ? 0 : -1;
        offset += (size_t)count;
    }
    return 1;
}

static int file_stream_read(void *context, unsigned char *buffer, size_t capacity) {
    FileStreamContext *file_stream = context;
    size_t count = fread(buffer, 1, capacity, file_stream->input);
    if (!count && ferror(file_stream->input)) return -1;
    return (int)count;
}

static int file_stream_write(void *context, const unsigned char *buffer, size_t length) {
    FileStreamContext *file_stream = context;
    size_t offset = 0;
    while (offset < length) {
        size_t count = fwrite(buffer + offset, 1, length - offset, file_stream->output);
        if (!count) return 0;
        offset += count;
    }
    return 1;
}

static int file_stream_flush(void *context) {
    FileStreamContext *file_stream = context;
    return fflush(file_stream->output) == 0;
}

static int socket_stream_read(void *context, unsigned char *buffer, size_t capacity) {
    SocketStreamContext *socket_stream = context;
#ifdef _WIN32
    int count;
    do {
        count = recv(socket_stream->socket, (char *)buffer, (int)capacity, 0);
    } while (count == SOCKET_ERROR && WSAGetLastError() == WSAEINTR);
    return count == SOCKET_ERROR ? -1 : count;
#else
    ssize_t count;
    do { count = recv(socket_stream->socket, buffer, capacity, 0); } while (count < 0 && errno == EINTR);
    return count < 0 ? -1 : (int)count;
#endif
}

static int socket_stream_write(void *context, const unsigned char *buffer, size_t length) {
    SocketStreamContext *socket_stream = context;
    size_t offset = 0;
    while (offset < length) {
    #ifdef _WIN32
        int count = send(socket_stream->socket, (const char *)buffer + offset, (int)(length - offset), 0);
        if (count == SOCKET_ERROR && WSAGetLastError() == WSAEINTR) continue;
        if (count == SOCKET_ERROR || !count) return 0;
    #else
#ifdef MSG_NOSIGNAL
        ssize_t count = send(socket_stream->socket, buffer + offset, length - offset, MSG_NOSIGNAL);
#else
        ssize_t count = send(socket_stream->socket, buffer + offset, length - offset, 0);
#endif
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return 0;
#endif
        offset += (size_t)count;
    }
    return 1;
}

static int socket_stream_flush(void *context) {
    (void)context;
    return 1;
}

static void close_gateway_socket(GatewaySocket socket_value) {
#ifdef _WIN32
    closesocket(socket_value);
#else
    close(socket_value);
#endif
}

static int split_tcp_endpoint(const char *endpoint, char *host, size_t host_capacity,
                              char *port, size_t port_capacity) {
    const char *port_start = NULL;
    size_t host_length = 0;
    if (*endpoint == '[') {
        const char *closing = strchr(endpoint, ']');
        if (!closing || closing[1] != ':') return 0;
        host_length = (size_t)(closing - endpoint - 1);
        port_start = closing + 2;
        endpoint++;
    } else {
        const char *separator = strrchr(endpoint, ':');
        if (!separator || memchr(endpoint, ':', (size_t)(separator - endpoint))) return 0;
        host_length = (size_t)(separator - endpoint);
        port_start = separator + 1;
    }
    size_t port_length = strlen(port_start);
    if (host_length >= host_capacity || !port_length || port_length >= port_capacity) return 0;
    for (size_t index = 0; index < port_length; index++)
        if (port_start[index] < '0' || port_start[index] > '9') return 0;
    unsigned long port_number = strtoul(port_start, NULL, 10);
    if (!port_number || port_number > 65535) return 0;
    memcpy(host, endpoint, host_length); host[host_length] = '\0';
    memcpy(port, port_start, port_length + 1);
    return 1;
}

static int open_tcp_listener(const char *endpoint, GatewaySocket *listener_out) {
    if (!endpoint || !*endpoint || !listener_out) return 2;
    char host[1024], port[16];
    if (!split_tcp_endpoint(endpoint, host, sizeof(host), port, sizeof(port))) {
        fputs("separan-gw: TCP listener must be tcp:<host>:<port> (IPv6 hosts use brackets)\n", stderr);
        return 2;
    }
#ifdef _WIN32
    WSADATA winsock_data;
    if (WSAStartup(MAKEWORD(2, 2), &winsock_data) != 0) {
        fputs("separan-gw: Winsock initialization failed\n", stderr); return 1;
    }
#endif
    struct addrinfo hints; memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM; hints.ai_flags = AI_PASSIVE;
    struct addrinfo *addresses = NULL;
    int lookup_status = getaddrinfo(!host[0] || !strcmp(host, "*") ? NULL : host, port, &hints, &addresses);
    if (lookup_status != 0) {
        fprintf(stderr, "separan-gw: cannot resolve TCP listener '%s'\n", endpoint);
#ifdef _WIN32
        WSACleanup();
#endif
        return 1;
    }
    GatewaySocket listener =
#ifdef _WIN32
        INVALID_SOCKET;
#else
        -1;
#endif
    for (struct addrinfo *address = addresses; address; address = address->ai_next) {
        GatewaySocket candidate = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
#ifdef _WIN32
        if (candidate == INVALID_SOCKET) continue;
        int exclusive = 1;
        setsockopt(candidate, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, (const char *)&exclusive, sizeof(exclusive));
        if (bind(candidate, address->ai_addr, (int)address->ai_addrlen) == 0 && listen(candidate, SOMAXCONN) == 0) {
#else
        if (candidate < 0) continue;
        int reuse = 1;
        setsockopt(candidate, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
        if (bind(candidate, address->ai_addr, (socklen_t)address->ai_addrlen) == 0 && listen(candidate, 128) == 0) {
#endif
            listener = candidate; break;
        }
        close_gateway_socket(candidate);
    }
    freeaddrinfo(addresses);
#ifdef _WIN32
    if (listener == INVALID_SOCKET) {
        fputs("separan-gw: cannot bind TCP listener\n", stderr); WSACleanup(); return 1;
    }
#else
    if (listener < 0) { perror("separan-gw: bind/listen TCP"); return 1; }
#endif
    *listener_out = listener;
    return 0;
}

int separan_gw_create_tcp_listener(const char *endpoint, uintptr_t *listener) {
    if (!listener) return 2;
    GatewaySocket created;
    int status = open_tcp_listener(endpoint, &created);
    if (status) return status;
    *listener = (uintptr_t)created;
    return 0;
}

int separan_gw_run_fastcgi_tcp_socket(separan_runtime *runtime, uintptr_t listener,
                                      const separan_gw_supervisor_options *options) {
    if (!runtime) return 2;
    int status = run_socket_endpoint(runtime, (GatewaySocket)listener, NULL, options);
#ifdef _WIN32
    WSACleanup();
#endif
    return status;
}

void separan_gw_close_tcp_listener(uintptr_t listener) {
    close_gateway_socket((GatewaySocket)listener);
#ifdef _WIN32
    WSACleanup();
#endif
}

int separan_gw_run_fastcgi_tcp(separan_runtime *runtime, const char *endpoint,
                               const separan_gw_supervisor_options *options) {
    if (!runtime) return 2;
    uintptr_t listener;
    int status = separan_gw_create_tcp_listener(endpoint, &listener);
    return status ? status : separan_gw_run_fastcgi_tcp_socket(runtime, listener, options);
}

#ifdef _WIN32
typedef struct { HANDLE pipe; } PipeStreamContext;
static volatile sig_atomic_t pipe_stop_requested;
static volatile sig_atomic_t tcp_stop_requested;

static BOOL WINAPI pipe_control_handler(DWORD event) {
    if (event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT || event == CTRL_CLOSE_EVENT ||
        event == CTRL_LOGOFF_EVENT || event == CTRL_SHUTDOWN_EVENT) {
        pipe_stop_requested = 1;
        return TRUE;
    }
    return FALSE;
}

static BOOL WINAPI tcp_control_handler(DWORD event) {
    if (event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT || event == CTRL_CLOSE_EVENT ||
        event == CTRL_LOGOFF_EVENT || event == CTRL_SHUTDOWN_EVENT) {
        tcp_stop_requested = 1;
        return TRUE;
    }
    return FALSE;
}

static int pipe_stream_read(void *context, unsigned char *buffer, size_t capacity) {
    PipeStreamContext *pipe_stream = context;
    DWORD count = 0;
    if (ReadFile(pipe_stream->pipe, buffer, (DWORD)capacity, &count, NULL)) return (int)count;
    return GetLastError() == ERROR_BROKEN_PIPE ? 0 : -1;
}

static int pipe_stream_write(void *context, const unsigned char *buffer, size_t length) {
    PipeStreamContext *pipe_stream = context;
    size_t offset = 0;
    while (offset < length) {
        DWORD count = 0;
        DWORD chunk = (DWORD)((length - offset) > MAXDWORD ? MAXDWORD : (length - offset));
        if (!WriteFile(pipe_stream->pipe, buffer + offset, chunk, &count, NULL) || !count) return 0;
        offset += count;
    }
    return 1;
}

static int pipe_stream_flush(void *context) { (void)context; return 1; }
#endif

int separan_gw_run_fastcgi_pipe(separan_runtime *runtime, const char *pipe_name,
                                const separan_gw_supervisor_options *options) {
#ifndef _WIN32
    (void)runtime; (void)pipe_name; (void)options;
    fputs("separan-gw: Windows named pipes are unavailable on this build\n", stderr);
    return 2;
#else
    if (!runtime || !pipe_name || !*pipe_name) return 2;
    char path[256];
    const char prefix[] = "\\\\.\\pipe\\";
    int length = !strncmp(pipe_name, prefix, sizeof(prefix) - 1)
        ? snprintf(path, sizeof(path), "%s", pipe_name)
        : snprintf(path, sizeof(path), "%s%s", prefix, pipe_name);
    if (length < 0 || (size_t)length >= sizeof(path)) {
        fputs("separan-gw: named pipe path is too long\n", stderr); return 2;
    }
    pipe_stop_requested = 0;
    SetConsoleCtrlHandler(pipe_control_handler, TRUE);
    WorkerLimits worker = {0, options ? options->max_requests : 0,
                           options ? options->max_memory_bytes : 0, &pipe_stop_requested};
    for (;;) {
        if (worker_should_recycle(&worker)) { SetConsoleCtrlHandler(pipe_control_handler, FALSE); return 0; }
        HANDLE pipe = CreateNamedPipeA(path, PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT, PIPE_UNLIMITED_INSTANCES,
            65536, 65536, 0, NULL);
        if (pipe == INVALID_HANDLE_VALUE) {
            fputs("separan-gw: CreateNamedPipe failed\n", stderr);
            SetConsoleCtrlHandler(pipe_control_handler, FALSE); return 1;
        }
        DWORD pipe_mode = PIPE_READMODE_BYTE | PIPE_NOWAIT;
        SetNamedPipeHandleState(pipe, &pipe_mode, NULL, NULL);
        BOOL connected = FALSE;
        while (!connected && !worker_should_recycle(&worker)) {
            connected = ConnectNamedPipe(pipe, NULL);
            if (!connected) {
                DWORD error = GetLastError();
                if (error == ERROR_PIPE_CONNECTED) connected = TRUE;
                else if (error == ERROR_PIPE_LISTENING) Sleep(25);
                else {
                    CloseHandle(pipe); fputs("separan-gw: ConnectNamedPipe failed\n", stderr);
                    SetConsoleCtrlHandler(pipe_control_handler, FALSE); return 1;
                }
            }
        }
        if (!connected) { CloseHandle(pipe); SetConsoleCtrlHandler(pipe_control_handler, FALSE); return 0; }
        pipe_mode = PIPE_READMODE_BYTE | PIPE_WAIT;
        SetNamedPipeHandleState(pipe, &pipe_mode, NULL, NULL);
        PipeStreamContext context = {pipe};
        FastcgiStream stream = {&context, pipe_stream_read, pipe_stream_write, pipe_stream_flush};
        int request_status = run_fastcgi_stream(runtime, &stream, &worker);
        FlushFileBuffers(pipe);
        DisconnectNamedPipe(pipe); CloseHandle(pipe);
        if (request_status == 2) { SetConsoleCtrlHandler(pipe_control_handler, FALSE); return 0; }
        if (request_status) { SetConsoleCtrlHandler(pipe_control_handler, FALSE); return request_status; }
    }
#endif
}

static int write_record(FastcgiStream *stream, unsigned char type, unsigned short request_id, const unsigned char *content, size_t length) {
    int empty_record = length == 0;
    while (length) {
        unsigned short part = (unsigned short)(length > FCGI_MAX_CONTENT ? FCGI_MAX_CONTENT : length);
        unsigned char header[8] = {FCGI_VERSION_1, type, (unsigned char)(request_id >> 8), (unsigned char)request_id,
                                   (unsigned char)(part >> 8), (unsigned char)part, 0, 0};
        if (!stream->write(stream->context, header, sizeof(header)) || !stream->write(stream->context, content, part)) return 0;
        content += part; length -= part;
    }
    if (empty_record) {
        unsigned char header[8] = {FCGI_VERSION_1, type, (unsigned char)(request_id >> 8), (unsigned char)request_id, 0, 0, 0, 0};
        if (!stream->write(stream->context, header, sizeof(header))) return 0;
    }
    return stream->flush(stream->context);
}

static int finish_request(FastcgiStream *stream, unsigned short request_id, unsigned app_status, unsigned char protocol_status) {
    unsigned char body[8] = {(unsigned char)(app_status >> 24), (unsigned char)(app_status >> 16),
        (unsigned char)(app_status >> 8), (unsigned char)app_status, protocol_status, 0, 0, 0};
    unsigned char header[8] = {FCGI_VERSION_1, FCGI_END_REQUEST, (unsigned char)(request_id >> 8), (unsigned char)request_id, 0, 8, 0, 0};
    return stream->write(stream->context, header, sizeof(header)) && stream->write(stream->context, body, sizeof(body)) && stream->flush(stream->context);
}

static int decode_request(separan_runtime *runtime, FastcgiStream *stream, unsigned short request_id, const Params *params, const Buffer *body) {
    Buffer json = {0}; char *response = NULL; size_t response_length = 0;
    int ok = request_json(params, body, &json);
    if (!ok || !buffer_append(&json, "", 1)) {
        free(json.data); write_record(stream, FCGI_STDERR, request_id, (const unsigned char *)"invalid FastCGI request parameters\n", strlen("invalid FastCGI request parameters\n"));
        write_record(stream, FCGI_STDERR, request_id, NULL, 0);
        return finish_request(stream, request_id, 1, FCGI_REQUEST_COMPLETE);
    }
    json.length--;
    int status = separan_runtime_dispatch_http_cgi(runtime, (const char *)json.data, &response, &response_length);
    free(json.data);
    if (status) {
        separan_runtime_diagnostic diagnostic; separan_runtime_get_diagnostic(runtime, &diagnostic);
        const char *message = diagnostic.description[0] ? diagnostic.description : "request failed";
        write_record(stream, FCGI_STDERR, request_id, (const unsigned char *)message, strlen(message));
        write_record(stream, FCGI_STDERR, request_id, NULL, 0);
        free(response);
        finish_request(stream, request_id, 1, FCGI_REQUEST_COMPLETE);
        return 0;
    }
    ok = response && write_record(stream, FCGI_STDOUT, request_id, (const unsigned char *)response, response_length) &&
         write_record(stream, FCGI_STDOUT, request_id, NULL, 0) && write_record(stream, FCGI_STDERR, request_id, NULL, 0);
    free(response);
    return ok && finish_request(stream, request_id, 0, FCGI_REQUEST_COMPLETE);
}

static size_t current_rss_bytes(void) {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS counters;
    if (!GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters))) return 0;
    return (size_t)counters.WorkingSetSize;
#else
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage) != 0 || usage.ru_maxrss < 0) return 0;
#ifdef __APPLE__
    return (size_t)usage.ru_maxrss;
#else
    if ((unsigned long long)usage.ru_maxrss > SIZE_MAX / 1024ULL) return SIZE_MAX;
    return (size_t)usage.ru_maxrss * 1024U;
#endif
#endif
}

static int worker_should_recycle(const WorkerLimits *worker) {
    if (!worker) return 0;
    if (worker->stop_requested && *worker->stop_requested) return 1;
    if (worker->max_requests && worker->requests >= worker->max_requests) return 1;
    return worker->max_memory_bytes && current_rss_bytes() >= worker->max_memory_bytes;
}

static int run_fastcgi_stream(separan_runtime *runtime, FastcgiStream *stream, WorkerLimits *worker) {
    unsigned char header[8]; unsigned short request_id = 0; unsigned short active_id = 0;
    Buffer params_data = {0}, body = {0}; Params params = {0}; int in_request = 0, params_done = 0;
    for (;;) {
        int read_status = read_exact(stream, header, sizeof(header), 1);
        if (!read_status) break;
        if (read_status < 0 || header[0] != FCGI_VERSION_1) goto failed;
        unsigned short id = (unsigned short)((header[2] << 8) | header[3]);
        size_t content_length = ((size_t)header[4] << 8) | header[5]; size_t padding_length = header[6];
        unsigned char *content = content_length ? malloc(content_length) : NULL;
        if (content_length && !content) goto failed;
        if (content_length && read_exact(stream, content, content_length, 0) != 1) { free(content); goto failed; }
        unsigned char padding[255]; if (padding_length && read_exact(stream, padding, padding_length, 0) != 1) { free(content); goto failed; }
        switch (header[1]) {
        case FCGI_GET_VALUES:
            free(content);
            if (!write_record(stream, FCGI_GET_VALUES_RESULT, 0, NULL, 0)) goto failed;
            break;
        case FCGI_BEGIN_REQUEST:
            if (content_length < 3 || in_request) { free(content); goto failed; }
            request_id = active_id = id;
            if ((((unsigned)content[0] << 8) | content[1]) != FCGI_RESPONDER) {
                free(content); if (!finish_request(stream, id, 0, FCGI_UNKNOWN_ROLE)) goto failed; break;
            }
            in_request = 1; params_done = 0; params_data.length = body.length = 0; params_free(&params);
            free(content); break;
        case FCGI_PARAMS:
            if (!in_request || id != active_id) { free(content); goto failed; }
            if (!content_length) { params_done = 1; if (!parse_params(&params_data, &params)) goto failed; }
            else if (params_done || !buffer_append(&params_data, content, content_length)) { free(content); goto failed; }
            free(content); break;
        case FCGI_STDIN:
            if (!in_request || id != active_id || !params_done) { free(content); goto failed; }
            if (!content_length) {
                free(content);
                if (!decode_request(runtime, stream, active_id, &params, &body)) goto failed;
                params_free(&params); params_data.length = body.length = 0; in_request = 0; active_id = request_id = 0;
                if (worker) worker->requests++;
                if (worker_should_recycle(worker)) goto recycled;
            } else if (!buffer_append(&body, content, content_length)) { free(content); goto failed; }
            free(content); break;
        case FCGI_ABORT_REQUEST:
            free(content); if (!finish_request(stream, id, 1, FCGI_REQUEST_COMPLETE)) goto failed;
            params_free(&params); params_data.length = body.length = 0; in_request = 0; active_id = 0;
            if (worker) worker->requests++;
            if (worker_should_recycle(worker)) goto recycled;
            break;
        default:
            free(content); break;
        }
    }
    params_free(&params); free(params_data.data); free(body.data); return 0;
recycled:
    params_free(&params); free(params_data.data); free(body.data); return 2;
failed:
    params_free(&params); free(params_data.data); free(body.data); return 1;
}

#ifndef _WIN32
static volatile sig_atomic_t worker_stop_requested;
static volatile sig_atomic_t supervisor_stop_requested;
static volatile sig_atomic_t supervisor_reload_requested;
static int serve_socket_connections(separan_runtime *runtime, GatewaySocket listener, WorkerLimits *worker);

static void request_worker_stop(int signal_number) {
    (void)signal_number;
    worker_stop_requested = 1;
}

static void request_supervisor_stop(int signal_number) {
    if (signal_number == SIGHUP) {
        supervisor_reload_requested = 1;
        supervisor_stop_requested = 1;
        worker_stop_requested = 1;
        return;
    }
    supervisor_stop_requested = 1;
}

static uint64_t monotonic_milliseconds(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 0;
    return (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
}

static void sleep_milliseconds(unsigned milliseconds) {
    struct timespec duration = {(time_t)(milliseconds / 1000), (long)(milliseconds % 1000) * 1000000L};
    while (nanosleep(&duration, &duration) < 0 && errno == EINTR) {}
}

static pid_t start_socket_worker(separan_runtime *runtime, GatewaySocket listener,
                                 const separan_gw_supervisor_options *options) {
    pid_t child = fork();
    if (child != 0) return child;
    worker_stop_requested = 0;
    struct sigaction action; memset(&action, 0, sizeof(action));
    action.sa_handler = request_worker_stop; sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL); sigaction(SIGINT, &action, NULL);
    WorkerLimits worker = {0, options->max_requests, options->max_memory_bytes, &worker_stop_requested};
    int status = 1;
    status = serve_socket_connections(runtime, listener, &worker);
    close_gateway_socket(listener);
    separan_runtime_destroy(runtime);
    _exit(status ? 1 : 0);
}

static int supervise_socket_workers(separan_runtime *runtime, GatewaySocket listener,
                                    const char *socket_path,
                                    const separan_gw_supervisor_options *options) {
    pid_t children[256] = {0};
    uint64_t restart_at[256] = {0};
    unsigned worker_count = options->workers ? options->workers : 1;
    supervisor_stop_requested = 0;
    supervisor_reload_requested = 0;
    struct sigaction action, previous_term, previous_int;
    memset(&action, 0, sizeof(action)); action.sa_handler = request_supervisor_stop; sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, &previous_term); sigaction(SIGINT, &action, &previous_int);
    struct sigaction reload_action, previous_hup;
    memset(&reload_action, 0, sizeof(reload_action)); reload_action.sa_handler = request_supervisor_stop;
    sigemptyset(&reload_action.sa_mask); sigaction(SIGHUP, &reload_action, &previous_hup);
    int startup_failed = 0;
    for (unsigned index = 0; index < worker_count; index++) {
        children[index] = start_socket_worker(runtime, listener, options);
        if (children[index] < 0) { perror("separan-gw: fork worker"); startup_failed = 1; break; }
    }
    if (startup_failed) supervisor_stop_requested = 1;
    while (!supervisor_stop_requested) {
        uint64_t now = monotonic_milliseconds();
        for (unsigned index = 0; index < worker_count; index++) {
            if (children[index]) {
                int status;
                pid_t finished = waitpid(children[index], &status, WNOHANG);
                if (finished == children[index] || (finished < 0 && errno == ECHILD)) {
                    children[index] = 0;
                    restart_at[index] = now + options->restart_backoff_ms;
                }
            }
            if (!children[index] && now >= restart_at[index]) {
                children[index] = start_socket_worker(runtime, listener, options);
                if (children[index] < 0) {
                    perror("separan-gw: restart worker");
                    restart_at[index] = now + (options->restart_backoff_ms ? options->restart_backoff_ms : 100);
                }
            }
        }
        sleep_milliseconds(25);
    }

    for (unsigned index = 0; index < worker_count; index++)
        if (children[index]) kill(children[index], SIGTERM);
    uint64_t deadline = monotonic_milliseconds() + options->restart_grace_ms;
    for (;;) {
        int remaining = 0;
        for (unsigned index = 0; index < worker_count; index++) {
            if (!children[index]) continue;
            int status;
            pid_t finished = waitpid(children[index], &status, WNOHANG);
            if (finished == children[index] || (finished < 0 && errno == ECHILD)) children[index] = 0;
            else remaining++;
        }
        if (!remaining || monotonic_milliseconds() >= deadline) break;
        sleep_milliseconds(25);
    }
    for (unsigned index = 0; index < worker_count; index++) {
        if (!children[index]) continue;
        kill(children[index], SIGKILL);
        waitpid(children[index], NULL, 0);
    }
    sigaction(SIGTERM, &previous_term, NULL); sigaction(SIGINT, &previous_int, NULL);
    sigaction(SIGHUP, &previous_hup, NULL);
    close_gateway_socket(listener);
    if (socket_path) unlink(socket_path);
    if (supervisor_reload_requested) return separan_gw_reload_process();
    return startup_failed ? 1 : 0;
}
#endif

static int serve_socket_connections(separan_runtime *runtime, GatewaySocket listener, WorkerLimits *worker) {
    for (;;) {
        if (worker_should_recycle(worker)) return 0;
#ifdef _WIN32
        if (worker && worker->stop_requested) {
            fd_set readable; FD_ZERO(&readable); FD_SET(listener, &readable);
            struct timeval wait = {0, 100000};
            int ready = select(0, &readable, NULL, NULL, &wait);
            if (ready == SOCKET_ERROR) {
                if (WSAGetLastError() == WSAEINTR) continue;
                fputs("separan-gw: TCP select failed\n", stderr); return 1;
            }
            if (!ready) continue;
        }
 #endif
        GatewaySocket client = accept(listener, NULL, NULL);
#ifdef _WIN32
        if (client == INVALID_SOCKET) {
            if (WSAGetLastError() == WSAEINTR) continue;
            fputs("separan-gw: accept failed\n", stderr); return 1;
        }
#else
        if (client < 0) {
            if (errno == EINTR && worker_should_recycle(worker)) return 0;
            if (errno == EINTR) continue;
            perror("separan-gw: accept"); return 1;
        }
#endif
        SocketStreamContext context = {client};
        FastcgiStream stream = {&context, socket_stream_read, socket_stream_write, socket_stream_flush};
        int status = run_fastcgi_stream(runtime, &stream, worker);
        close_gateway_socket(client);
        if (status == 2) return 0;
        if (status) return status;
    }
}

static int run_socket_endpoint(separan_runtime *runtime, GatewaySocket listener,
                               const char *socket_path, const separan_gw_supervisor_options *options) {
#ifndef _WIN32
    if (options && options->enabled)
        return supervise_socket_workers(runtime, listener, socket_path, options);
    worker_stop_requested = 0;
    struct sigaction action, previous_term, previous_int;
    memset(&action, 0, sizeof(action)); action.sa_handler = request_worker_stop; sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, &previous_term); sigaction(SIGINT, &action, &previous_int);
    struct sigaction reload_action, previous_hup;
    memset(&reload_action, 0, sizeof(reload_action)); reload_action.sa_handler = request_supervisor_stop;
    sigemptyset(&reload_action.sa_mask); sigaction(SIGHUP, &reload_action, &previous_hup);
    WorkerLimits worker = {0, options ? options->max_requests : 0,
                           options ? options->max_memory_bytes : 0, &worker_stop_requested};
    int status = serve_socket_connections(runtime, listener, &worker);
    sigaction(SIGTERM, &previous_term, NULL); sigaction(SIGINT, &previous_int, NULL);
    sigaction(SIGHUP, &previous_hup, NULL);
    close_gateway_socket(listener);
    if (socket_path) unlink(socket_path);
    if (supervisor_stop_requested && supervisor_reload_requested) return separan_gw_reload_process();
    return status;
#else
    (void)socket_path;
    if (options && options->enabled) {
        fputs("separan-gw: Windows TCP process supervision requires named-pipe transport\n", stderr);
        close_gateway_socket(listener); return 2;
    }
    tcp_stop_requested = 0;
    SetConsoleCtrlHandler(tcp_control_handler, TRUE);
    WorkerLimits worker = {0, options ? options->max_requests : 0,
                           options ? options->max_memory_bytes : 0, &tcp_stop_requested};
    int status = serve_socket_connections(runtime, listener, &worker);
    SetConsoleCtrlHandler(tcp_control_handler, FALSE);
    close_gateway_socket(listener);
    return status;
#endif
}

int separan_gw_run_fastcgi_stdio(separan_runtime *runtime) {
    if (!runtime) return 1;
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 || _setmode(_fileno(stdout), _O_BINARY) == -1) return 1;
#endif
    FileStreamContext context = {stdin, stdout};
    FastcgiStream stream = {&context, file_stream_read, file_stream_write, file_stream_flush};
    return run_fastcgi_stream(runtime, &stream, NULL);
}

int separan_gw_run_fastcgi_unix(separan_runtime *runtime, const char *socket_path,
                                const separan_gw_supervisor_options *options) {
#ifdef _WIN32
    (void)runtime; (void)socket_path; (void)options;
    fputs("separan-gw: Unix-domain sockets are unavailable on this build\n", stderr);
    return 2;
#else
    if (!runtime || !socket_path || !*socket_path) return 2;
    if (strlen(socket_path) >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        fputs("separan-gw: Unix socket path is too long\n", stderr); return 2;
    }
    int listener = socket(AF_UNIX, SOCK_STREAM, 0);
    if (listener < 0) { perror("separan-gw: socket"); return 1; }
    struct sockaddr_un address; memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX; snprintf(address.sun_path, sizeof(address.sun_path), "%s", socket_path);
    struct stat existing;
    if (lstat(socket_path, &existing) == 0) {
        if (!S_ISSOCK(existing.st_mode)) {
            fprintf(stderr, "separan-gw: socket path exists and is not a socket: %s\n", socket_path);
            close(listener); return 1;
        }
        int probe = socket(AF_UNIX, SOCK_STREAM, 0);
        if (probe < 0) { perror("separan-gw: socket probe"); close(listener); return 1; }
        int connect_status = connect(probe, (struct sockaddr *)&address, sizeof(address));
        int connect_error = errno;
        close(probe);
        if (connect_status == 0) {
            fprintf(stderr, "separan-gw: socket is already in use: %s\n", socket_path);
            close(listener); return 1;
        }
        if (connect_error != ECONNREFUSED && connect_error != ENOENT) {
            errno = connect_error; perror("separan-gw: socket probe"); close(listener); return 1;
        }
        if (unlink(socket_path) < 0) { perror("separan-gw: remove stale socket"); close(listener); return 1; }
    } else if (errno != ENOENT) {
        perror("separan-gw: inspect socket path"); close(listener); return 1;
    }
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) < 0 || chmod(socket_path, 0660) < 0 || listen(listener, 128) < 0) {
        perror("separan-gw: bind/listen"); close(listener); unlink(socket_path); return 1;
    }
    return run_socket_endpoint(runtime, listener, socket_path, options);
#endif
}
