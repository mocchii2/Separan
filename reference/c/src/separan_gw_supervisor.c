#include "separan_gw_transport.h"

#include <stdio.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <psapi.h>
#include <string.h>

typedef struct {
    PROCESS_INFORMATION process;
    ULONGLONG restart_at;
    ULONGLONG stop_at;
    int stopping;
} GatewayChild;

static volatile LONG supervisor_stop_requested;
static volatile LONG supervisor_reload_requested;
static SERVICE_STATUS_HANDLE service_status_handle;
static SERVICE_STATUS service_status;

static void report_service_status(DWORD state, DWORD win32_exit, DWORD wait_hint) {
    if (!service_status_handle) return;
    service_status.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    service_status.dwCurrentState = state;
    service_status.dwWin32ExitCode = win32_exit;
    service_status.dwWaitHint = wait_hint;
    service_status.dwControlsAccepted = state == SERVICE_RUNNING
        ? SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN | SERVICE_ACCEPT_PARAMCHANGE
        : 0;
    SetServiceStatus(service_status_handle, &service_status);
}

static DWORD WINAPI service_control_handler(DWORD control, DWORD event_type, LPVOID event_data, LPVOID context) {
    (void)event_type; (void)event_data; (void)context;
    if (control == SERVICE_CONTROL_STOP || control == SERVICE_CONTROL_SHUTDOWN) {
        InterlockedExchange(&supervisor_stop_requested, 1);
        report_service_status(SERVICE_STOP_PENDING, NO_ERROR, 10000);
    } else if (control == SERVICE_CONTROL_PARAMCHANGE) {
        InterlockedExchange(&supervisor_reload_requested, 1);
        InterlockedExchange(&supervisor_stop_requested, 1);
    } else if (control == SERVICE_CONTROL_INTERROGATE) {
        SetServiceStatus(service_status_handle, &service_status);
    }
    return NO_ERROR;
}

static void WINAPI gateway_service_main(DWORD argument_count, LPSTR *arguments);
static char *service_argv[6];
static char *service_transport;
static char *service_endpoint;
static const separan_gw_supervisor_options *service_options;

static BOOL WINAPI supervisor_console_handler(DWORD event) {
    if (event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT || event == CTRL_CLOSE_EVENT ||
        event == CTRL_LOGOFF_EVENT || event == CTRL_SHUTDOWN_EVENT) {
        InterlockedExchange(&supervisor_stop_requested, 1);
        return TRUE;
    }
    return FALSE;
}

static void WINAPI gateway_service_main(DWORD argument_count, LPSTR *arguments) {
    (void)argument_count; (void)arguments;
    service_status_handle = RegisterServiceCtrlHandlerExA("separan-gw", service_control_handler, NULL);
    if (!service_status_handle) return;
    report_service_status(SERVICE_START_PENDING, NO_ERROR, 10000);
    report_service_status(SERVICE_RUNNING, NO_ERROR, 0);
    AllocConsole();
    int result = separan_gw_supervise_windows(service_argv[0], service_transport,
                                               service_endpoint, service_options);
    FreeConsole();
    report_service_status(SERVICE_STOPPED, result ? ERROR_SERVICE_SPECIFIC_ERROR : NO_ERROR, 0);
}

int separan_gw_run_windows_service(const char *config_path, const char *transport,
                                  const char *endpoint,
                                  const separan_gw_supervisor_options *options) {
    if (!config_path || !transport || !options) return 2;
    service_argv[0] = (char *)config_path;
    service_transport = (char *)transport;
    service_endpoint = (char *)endpoint;
    service_options = options;
    SERVICE_TABLE_ENTRYA table[] = {{"separan-gw", gateway_service_main}, {NULL, NULL}};
    if (!StartServiceCtrlDispatcherA(table)) {
        fprintf(stderr, "separan-gw: StartServiceCtrlDispatcher failed (%lu)\n", (unsigned long)GetLastError());
        return 1;
    }
    return service_status.dwWin32ExitCode == NO_ERROR ? 0 : 1;
}

static int child_running(GatewayChild *child) {
    if (!child->process.hProcess) return 0;
    DWORD status = 0;
    if (!GetExitCodeProcess(child->process.hProcess, &status) || status != STILL_ACTIVE) {
        CloseHandle(child->process.hThread);
        CloseHandle(child->process.hProcess);
        ZeroMemory(&child->process, sizeof(child->process));
        child->stopping = 0;
        return 0;
    }
    return 1;
}

static int write_all(HANDLE pipe, const void *buffer, size_t length) {
    const unsigned char *bytes = buffer;
    size_t offset = 0;
    while (offset < length) {
        DWORD written = 0;
        DWORD chunk = (DWORD)((length - offset) > MAXDWORD ? MAXDWORD : (length - offset));
        if (!WriteFile(pipe, bytes + offset, chunk, &written, NULL) || !written) return 0;
        offset += written;
    }
    return 1;
}

static int start_child(const char *config_path, const char *executable, const char *transport,
                       uintptr_t tcp_listener, unsigned slot, unsigned generation,
                       GatewayChild *child) {
    char control_name[256] = {0};
    HANDLE control_pipe = INVALID_HANDLE_VALUE;
    int is_tcp = !strcmp(transport, "fastcgi-tcp");
    if (is_tcp) {
        snprintf(control_name, sizeof(control_name), "\\\\.\\pipe\\SeparanGw-%lu-%u-%u",
                 (unsigned long)GetCurrentProcessId(), slot, generation);
        control_pipe = CreateNamedPipeA(control_name, PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT, 1,
            sizeof(WSAPROTOCOL_INFO), sizeof(WSAPROTOCOL_INFO), 0, NULL);
        if (control_pipe == INVALID_HANDLE_VALUE) return 0;
    }
    char command[32768];
    int length = is_tcp
        ? snprintf(command, sizeof(command), "\"%s\" --config \"%s\" --internal-worker --inherited-listener-pipe \"%s\"",
                   executable, config_path, control_name)
        : snprintf(command, sizeof(command), "\"%s\" --config \"%s\" --internal-worker", executable, config_path);
    if (length < 0 || (size_t)length >= sizeof(command)) {
        if (control_pipe != INVALID_HANDLE_VALUE) CloseHandle(control_pipe);
        return 0;
    }
    STARTUPINFOA startup; ZeroMemory(&startup, sizeof(startup));
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process; ZeroMemory(&process, sizeof(process));
    if (!CreateProcessA(executable, command, NULL, NULL, TRUE, CREATE_NEW_PROCESS_GROUP,
                        NULL, NULL, &startup, &process)) {
        if (control_pipe != INVALID_HANDLE_VALUE) CloseHandle(control_pipe);
        return 0;
    }
    if (is_tcp) {
        WSAPROTOCOL_INFO protocol_info;
        BOOL connected = ConnectNamedPipe(control_pipe, NULL);
        if ((!connected && GetLastError() != ERROR_PIPE_CONNECTED) ||
            WSADuplicateSocket((SOCKET)tcp_listener, process.dwProcessId, &protocol_info) != 0 ||
            !write_all(control_pipe, &protocol_info, sizeof(protocol_info))) {
            TerminateProcess(process.hProcess, 1); WaitForSingleObject(process.hProcess, 5000);
            CloseHandle(process.hThread); CloseHandle(process.hProcess); CloseHandle(control_pipe);
            return 0;
        }
        FlushFileBuffers(control_pipe); DisconnectNamedPipe(control_pipe); CloseHandle(control_pipe);
    }
    child->process = process;
    child->stopping = 0;
    return 1;
}

int separan_gw_receive_windows_tcp_socket(const char *control_name, uintptr_t *listener) {
    if (!control_name || !*control_name || !listener) return 2;
    WSADATA data;
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) return 1;
    HANDLE pipe = INVALID_HANDLE_VALUE;
    ULONGLONG deadline = GetTickCount64() + 10000;
    while (pipe == INVALID_HANDLE_VALUE && GetTickCount64() < deadline) {
        pipe = CreateFileA(control_name, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
        if (pipe == INVALID_HANDLE_VALUE) WaitNamedPipeA(control_name, 100);
    }
    if (pipe == INVALID_HANDLE_VALUE) { WSACleanup(); return 1; }
    WSAPROTOCOL_INFO protocol_info; unsigned char *bytes = (unsigned char *)&protocol_info;
    size_t offset = 0;
    while (offset < sizeof(protocol_info)) {
        DWORD received = 0;
        if (!ReadFile(pipe, bytes + offset, (DWORD)(sizeof(protocol_info) - offset), &received, NULL) || !received) {
            CloseHandle(pipe); WSACleanup(); return 1;
        }
        offset += received;
    }
    CloseHandle(pipe);
    SOCKET socket_value = WSASocket(FROM_PROTOCOL_INFO, FROM_PROTOCOL_INFO, FROM_PROTOCOL_INFO,
                                   &protocol_info, 0, WSA_FLAG_OVERLAPPED);
    if (socket_value == INVALID_SOCKET) { WSACleanup(); return 1; }
    *listener = (uintptr_t)socket_value;
    return 0;
}

static void request_child_stop(GatewayChild *child, unsigned grace_ms) {
    if (!child->process.hProcess || child->stopping) return;
    GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, child->process.dwProcessId);
    child->stopping = 1;
    child->stop_at = GetTickCount64() + grace_ms;
}

static void terminate_child(GatewayChild *child) {
    if (!child->process.hProcess) return;
    TerminateProcess(child->process.hProcess, 1);
    WaitForSingleObject(child->process.hProcess, 5000);
    CloseHandle(child->process.hThread);
    CloseHandle(child->process.hProcess);
    ZeroMemory(&child->process, sizeof(child->process));
    child->stopping = 0;
}

int separan_gw_supervise_windows(const char *config_path, const char *transport,
                                 const char *endpoint,
                                 const separan_gw_supervisor_options *options) {
    if (!config_path || !*config_path || !transport || !options ||
        (strcmp(transport, "fastcgi-pipe") && strcmp(transport, "fastcgi-tcp"))) return 2;
    char executable[32768];
    DWORD executable_length = GetModuleFileNameA(NULL, executable, sizeof(executable));
    if (!executable_length || executable_length >= sizeof(executable)) {
        fputs("separan-gw: cannot determine executable path for supervisor\n", stderr); return 1;
    }
    char full_config[32768];
    DWORD config_length = GetFullPathNameA(config_path, sizeof(full_config), full_config, NULL);
    if (!config_length || config_length >= sizeof(full_config) || strchr(full_config, '"')) {
        fputs("separan-gw: invalid config path for supervisor\n", stderr); return 2;
    }
    uintptr_t tcp_listener = 0;
    if (!strcmp(transport, "fastcgi-tcp") &&
        separan_gw_create_tcp_listener(endpoint, &tcp_listener) != 0) return 1;
    unsigned worker_count = options->workers ? options->workers : 1;
    GatewayChild children[256]; ZeroMemory(children, sizeof(children));
    unsigned generations[256] = {0};
    InterlockedExchange(&supervisor_stop_requested, 0);
    if (!SetConsoleCtrlHandler(supervisor_console_handler, TRUE)) {
        fputs("separan-gw: cannot install console shutdown handler\n", stderr);
        if (tcp_listener) separan_gw_close_tcp_listener(tcp_listener);
        return 1;
    }
    int startup_failed = 0;
    for (unsigned index = 0; index < worker_count; index++) {
        if (!start_child(full_config, executable, transport, tcp_listener, index,
                         ++generations[index], &children[index])) {
            fputs("separan-gw: cannot start transport worker\n", stderr);
            startup_failed = 1; InterlockedExchange(&supervisor_stop_requested, 1); break;
        }
    }
    if (!startup_failed) {
        while (!InterlockedCompareExchange(&supervisor_stop_requested, 0, 0)) {
            ULONGLONG now = GetTickCount64();
            for (unsigned index = 0; index < worker_count; index++) {
                GatewayChild *child = &children[index];
                if (child->process.hProcess && !child_running(child))
                    child->restart_at = now + options->restart_backoff_ms;
                if (child->process.hProcess && options->max_memory_bytes && !child->stopping) {
                    PROCESS_MEMORY_COUNTERS counters;
                    if (GetProcessMemoryInfo(child->process.hProcess, &counters, sizeof(counters)) &&
                        counters.WorkingSetSize >= options->max_memory_bytes)
                        request_child_stop(child, options->restart_grace_ms);
                }
                if (child->process.hProcess && child->stopping && now >= child->stop_at) {
                    terminate_child(child);
                    child->restart_at = now + options->restart_backoff_ms;
                }
                if (!child->process.hProcess && now >= child->restart_at &&
                    !start_child(full_config, executable, transport, tcp_listener, index,
                                 ++generations[index], child))
                    child->restart_at = now + (options->restart_backoff_ms ? options->restart_backoff_ms : 100);
            }
            Sleep(25);
        }
    }

    for (unsigned index = 0; index < worker_count; index++)
        request_child_stop(&children[index], options->restart_grace_ms);
    ULONGLONG deadline = GetTickCount64() + options->restart_grace_ms;
    for (;;) {
        unsigned active = 0;
        for (unsigned index = 0; index < worker_count; index++)
            if (child_running(&children[index])) active++;
        if (!active || GetTickCount64() >= deadline) break;
        Sleep(25);
    }
    for (unsigned index = 0; index < worker_count; index++) terminate_child(&children[index]);
    SetConsoleCtrlHandler(supervisor_console_handler, FALSE);
    if (tcp_listener) separan_gw_close_tcp_listener(tcp_listener);
    if (InterlockedExchange(&supervisor_reload_requested, 0)) {
        InterlockedExchange(&supervisor_stop_requested, 0);
        return separan_gw_supervise_windows(config_path, transport, endpoint, options);
    }
    return startup_failed ? 1 : 0;
}
#else
int separan_gw_receive_windows_tcp_socket(const char *control_pipe, uintptr_t *listener) {
    (void)control_pipe; (void)listener;
    fputs("separan-gw: inherited TCP sockets are only available on Windows\n", stderr);
    return 2;
}

int separan_gw_supervise_windows(const char *config_path, const char *transport, const char *endpoint,
                                 const separan_gw_supervisor_options *options) {
    (void)config_path; (void)transport; (void)endpoint; (void)options;
    fputs("separan-gw: Windows process supervision is unavailable on this build\n", stderr);
    return 2;
}

int separan_gw_run_windows_service(const char *config_path, const char *transport, const char *endpoint,
                                  const separan_gw_supervisor_options *options) {
    (void)config_path; (void)transport; (void)endpoint; (void)options;
    fputs("separan-gw: Windows services are unavailable on this build\n", stderr);
    return 2;
}
#endif