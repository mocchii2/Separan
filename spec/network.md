# Separan Native Network Specification v0.1

Status: experimental implementation in Separan `0.2.0-alpha.11`.

## Purpose and boundary

The native network API serves desktop and server scripts. It is separate from
HTTP and from the Embedded/Micro Separan driver layer. This specification does
not define board Wi-Fi drivers, GPIO-connected Ethernet controllers, firmware
generation, access-point hosting, or hardware safety validation.

Separan separates three authorities:

- `inspect_network`: read host interface state;
- `configure_network`: request IP configuration changes through an explicit adapter;
- `network`: resolve or contact explicitly allowed destination hosts and ports;
- `bind_network`: bind a UDP socket to an explicitly allowed local address and port.

No operation gains authority from a source program. The host creates the
capability and may additionally bound timeout and receive sizes. Private,
loopback, link-local, and other non-global destinations are rejected unless
`allow_private_network` is enabled.

## Dedicated values

`ip_address(text)` creates an immutable IPv4 or IPv6 value. Invalid text is an
`E970` error; no invalid address is kept as a string.

```separan
address = ip_address("192.168.1.10")

print ip_address_version(address)
print ip_address_is_private(address)
print ip_address_is_loopback(address)
print ip_address_is_global(address)
```

Other public values are `network_interface`, `tcp_connection`, and
`udp_socket`. TCP and UDP resources are closed by `tcp_close`/`udp_close`, and
the runtime also closes all still-open resources on termination.

## Interface inspection

```separan
interfaces = network_interfaces()
wifi = network_interface("Wi-Fi")

print network_is_connected(wifi)
print network_ip_address(wifi)
print network_ip_addresses(wifi)
print network_gateway(wifi)
print network_subnet_mask(wifi)
print network_dns_servers(wifi)
print network_mac_address(wifi)
print network_hostname()
```

`network_ip_address` is the preferred non-loopback IPv4 address when one is
available, then the first address. `network_ip_addresses` exposes the complete
snapshot so the singular function never hides the existence of additional
IPv4 or IPv6 addresses. Missing singular values are `null`; missing collections
are empty lists.

`network_status(interface)` returns an immutable object containing `name`,
`kind`, `connected`, `ip_address`, `gateway`, `subnet_mask`, `dns_servers`, and
`mac_address`. Interface kinds are `ethernet`, `wifi`, `loopback`, or `other`.

Preferred order is runtime-local and never rewrites operating-system routing:

```separan
network_set_preferred_interfaces(["Ethernet", "Wi-Fi"])
active = network_preferred_interface()
```

The result is the first currently connected interface in that order, or null.

## Ethernet and Wi-Fi views

`ethernet_open([name])` and `wifi_open([name])` select an existing host
interface; they do not open hardware or change OS configuration.

```separan
wifi = wifi_open()

print wifi_is_connected(wifi)
print wifi_ssid(wifi)
print wifi_bssid(wifi)
print wifi_channel(wifi)
print wifi_signal_strength(wifi)

networks = wifi_scan(wifi)
```

Each scan record contains `ssid`, `signal_strength`, `channel`, `bssid`, and
`security`. Results are ordered by decreasing signal and then SSID. The native
preview performs scanning through NetworkManager `nmcli` on Linux. A platform
without a safe native scanner reports `network_operation_unavailable`; it does
not return a fabricated empty scan.

`wifi_wait_until_connected(wifi, timeout)` polls the immutable interface
identity against fresh host state and returns boolean. Zero duration performs a
single check.

Joining/leaving Wi-Fi, setting the machine hostname, and starting an access
point remain outside this native preview. They have separate credential and
machine-wide policy requirements.

## Common IP address configuration

Address configuration is independent of link type. The same API accepts an
Ethernet or Wi-Fi `network_interface`:

```separan
function:main

lan = ethernet_open()
network_use_dhcp(lan)

if network_wait_until_addressed(lan, duration("10s")) :address_ready
print network_ip_address(lan)
else:address_ready
print "DHCP failed"
endif:address_ready

end_function:main
```

The public configuration operations are:

- `network_use_dhcp(interface)`;
- `network_set_static_address(interface, address, prefix, gateway, dns)`;
- `network_use_link_local(interface)`;
- `network_refresh_address(interface)` and `network_release_address(interface)`;
- `network_enable_link_local_fallback(interface)` and
  `network_disable_link_local_fallback(interface)`.

Static addresses and gateways must use the same IP version. Prefix length is
validated against that version. The gateway may be null and DNS is an explicit,
duplicate-free list. A static link-local address is rejected because
`network_use_link_local` names that policy directly.

`network_address_mode(interface)` returns exactly `disabled`, `dhcp`, `static`,
`link_local`, or `unknown`. `unknown` means that a read-only host inspector
cannot prove how the observed address was configured; Separan does not guess.

`network_dhcp_status(interface)` returns one of `disabled`, `discovering`,
`requesting`, `bound`, `renewing`, `rebinding`, or `failed`.
`network_dhcp_lease(interface)` returns null when no lease is available, or an
immutable object containing:

- `address`, `prefix`, `gateway`, and `dns_servers`;
- `server_address`;
- nullable `lease_duration`, `renew_after`, and `rebind_after` durations;
- nullable UTC `expires_at` datetime.

Adapter data is type-, range-, and ordering-validated. An invalid lease is
`E980 network_address_error`, never a partially trusted object.

Link-local fallback is disabled by default. Separan never changes a failed DHCP
request into a 169.254/16 address unless the program explicitly enables the
fallback. Explicit link-local mode and fallback both delegate duplicate-address
detection to the adapter's network stack.

Configuration requires the separate `configure_network` capability. The CLI
flag is `--allow-network-configuration`; it also permits the interface inspection
needed to select a target, but does not grant outbound network access. The
default desktop `NativeNetworkAdapter` remains read-only and returns
`network_operation_unavailable` for configuration. A host or embedded runtime
implements this adapter contract:

```text
use_dhcp(interface_name)
set_static_address(interface_name, configuration)
use_link_local(interface_name)
refresh_address(interface_name)
release_address(interface_name)
set_link_local_fallback(interface_name, enabled)
```

The adapter calls NetworkManager/OS-native configuration, lwIP, Pico SDK,
ESP-IDF, or an Arduino network stack. Separan owns intent, state names, typed
results, timeout, capability checks, and diagnostics; it does not implement a
second DHCP client. This model follows the DHCP client state and lease model in
[RFC 2131](https://www.rfc-editor.org/rfc/rfc2131) and keeps IPv4 link-local
behavior explicit as described by [RFC 3927](https://www.rfc-editor.org/rfc/rfc3927).
The complete source template is
[`examples/network_addressing.sep`](../examples/network_addressing.sep).

## DNS

```separan
addresses = dns_resolve("api.example.com")
name = dns_reverse_lookup(ip_address("203.0.113.10"))
```

`dns_resolve` returns a deterministic, duplicate-free `list<ip_address>` rather
than selecting an arbitrary DNS answer. Failure to resolve is
`network_dns_error`. Reverse lookup absence is a normal `null`.

Both operations enforce the network host allowlist and private-address rule.

## TCP

```separan
connection = tcp_connect(
    "192.168.1.20",
    502,
    timeout = duration("5s")
)

tcp_send(connection, request_bytes)
reply = tcp_receive(connection, 4096)
tcp_close(connection)
```

`tcp_send` accepts string (UTF-8 encoded) or bytes and returns the byte count.
`tcp_receive` always returns bytes, including empty bytes at orderly EOF.
Text decoding is explicit through `string_from_bytes`. Destination resolution
is validated before connecting, and the connection is made to that validated
numeric address.

## UDP

```separan
socket = udp_open(timeout = duration("5s"))
udp_send(socket, "192.168.1.50", 9999, payload)
packet = udp_receive(socket, 65536)

print packet.address
print packet.port
print packet.data

udp_close(socket)
```

`packet.data` is bytes, `packet.address` is `ip_address`, and `packet.port` is a
number. A receive-before-send endpoint may explicitly bind:

```separan
socket = udp_open(
    local_address = "127.0.0.1",
    local_port = 9000
)
```

Binding requires the separate `bind_network` capability and local address/port
allowlists. Supplying only one of `local_address` or `local_port` is an error.

## Errors and limits

All specialized failures are catchable as `network_error`:

- `network_dns_error`
- `network_interface_error`
- `network_connection_error`
- `network_timeout_error`
- `network_limit_error`
- `network_closed_error`
- `network_protocol_error`
- `network_operation_unavailable`
- `network_address_error`

Capability rejection is `permission_error`, not `network_error`. This keeps
host policy distinguishable from a failed network operation.

The native Windows implementation uses the IP Helper API without requiring
PowerShell or administrator access. Linux uses `ip` JSON data and
`/etc/resolv.conf`, with a conservative standard-library fallback on other
platforms.
