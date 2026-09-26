#ifndef SEPARAN_GW_TRANSPORT_H
#define SEPARAN_GW_TRANSPORT_H

#include "separan_runtime.h"
#include <stddef.h>
#include <stdint.h>

typedef struct {
	unsigned workers;
	size_t max_memory_bytes;
	size_t max_requests;
	unsigned restart_grace_ms;
	unsigned restart_backoff_ms;
	int enabled;
} separan_gw_supervisor_options;

int separan_gw_run_fastcgi_stdio(separan_runtime *runtime);
int separan_gw_run_fastcgi_unix(separan_runtime *runtime, const char *socket_path,
								const separan_gw_supervisor_options *options);
int separan_gw_run_fastcgi_tcp(separan_runtime *runtime, const char *endpoint,
							   const separan_gw_supervisor_options *options);
int separan_gw_create_tcp_listener(const char *endpoint, uintptr_t *listener);
int separan_gw_run_fastcgi_tcp_socket(separan_runtime *runtime, uintptr_t listener,
									  const separan_gw_supervisor_options *options);
void separan_gw_close_tcp_listener(uintptr_t listener);
int separan_gw_run_fastcgi_pipe(separan_runtime *runtime, const char *pipe_name,
								const separan_gw_supervisor_options *options);
int separan_gw_receive_windows_tcp_socket(const char *control_pipe, uintptr_t *listener);
int separan_gw_supervise_windows(const char *config_path, const char *transport,
								 const char *endpoint,
								 const separan_gw_supervisor_options *options);
int separan_gw_run_windows_service(const char *config_path, const char *transport,
								  const char *endpoint,
								  const separan_gw_supervisor_options *options);
int separan_gw_reload_process(void);

#endif
