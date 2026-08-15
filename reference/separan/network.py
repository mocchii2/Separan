"""Capability-gated native network inspection, DNS, TCP, and UDP APIs."""

from dataclasses import dataclass
import ctypes
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time

from .errors import error
from .objects import ObjectValue
from .randomness import BytesValue
from .system_utilities import UtilityFunction
from .temporal import DurationValue


DEFAULT_TIMEOUT = DurationValue(30_000)
DEFAULT_RECEIVE_BYTES = 65_536


@dataclass(frozen=True)
class IpAddressValue:
    value: object


@dataclass(frozen=True)
class NetworkInterfaceValue(ObjectValue):
    pass


@dataclass
class TcpConnectionValue:
    native: object
    host: str
    port: int
    closed: bool = False


@dataclass
class UdpSocketValue:
    native: object
    local_address: str | None
    local_port: int | None
    closed: bool = False


def _list(value):
    if value is None:
        return []
    return value if type(value) is list else [value]


def _kind(name, description="", addresses=()):
    text = f"{name} {description}".casefold()
    if any(word in text for word in ("wi-fi", "wifi", "wireless", "wlan", "802.11")):
        return "wifi"
    if any(word in text for word in ("loopback", "lo0")) or name.casefold() == "lo":
        return "loopback"
    if any(str(value).startswith("127.") or str(value) == "::1" for value in addresses):
        return "loopback"
    if any(word in text for word in ("ethernet", "eth", "enp", "eno", "enx")):
        return "ethernet"
    return "other"


def _dns_from_resolv_conf():
    path = Path("/etc/resolv.conf")
    if not path.is_file():
        return []
    result = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                result.append(parts[1])
    except OSError:
        return []
    return result


class NativeNetworkAdapter:
    """Read-only host adapter. Configuration changes remain host-owned."""

    def interfaces(self):
        system = platform.system().casefold()
        if system == "windows":
            found = self._windows_interfaces()
        elif system == "linux":
            found = self._linux_interfaces()
        else:
            found = []
        return found or self._fallback_interfaces()

    @staticmethod
    def _fallback_interfaces():
        try:
            indexed = socket.if_nameindex()
        except (AttributeError, OSError):
            indexed = []
        return [
            {
                "name": name,
                "index": index,
                "description": name,
                "kind": _kind(name),
                "connected": False,
                "addresses": [],
                "prefixes": [],
                "gateways": [],
                "dns_servers": _dns_from_resolv_conf(),
                "mac_address": None,
            }
            for index, name in indexed
        ]

    @staticmethod
    def _windows_interfaces():
        native = NativeNetworkAdapter._windows_ip_helper_interfaces()
        if native:
            return native
        executable = shutil.which("powershell") or shutil.which("pwsh")
        if executable is None:
            return []
        script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = @(Get-NetAdapter | ForEach-Object {
  $adapter = $_
  $config = Get-NetIPConfiguration -InterfaceIndex $adapter.ifIndex
  $profile = Get-NetConnectionProfile -InterfaceIndex $adapter.ifIndex
  $addresses = @()
  foreach ($item in @($config.IPv4Address)) { if ($item) { $addresses += [pscustomobject]@{address=$item.IPAddress; prefix=[int]$item.PrefixLength} } }
  foreach ($item in @($config.IPv6Address)) { if ($item) { $addresses += [pscustomobject]@{address=$item.IPAddress; prefix=[int]$item.PrefixLength} } }
  [pscustomobject]@{
    name = [string]$adapter.Name
    index = [int]$adapter.ifIndex
    description = [string]$adapter.InterfaceDescription
    connected = ($adapter.Status -eq 'Up')
    addresses = @($addresses)
    gateways = @(@($config.IPv4DefaultGateway).NextHop) + @(@($config.IPv6DefaultGateway).NextHop)
    dns_servers = @($config.DNSServer.ServerAddresses)
    mac_address = [string]$adapter.MacAddress
    ssid = if ($profile -and $adapter.Name -match 'Wi-Fi|Wireless|WLAN') { [string]$profile.Name } else { $null }
  }
})
$items | ConvertTo-Json -Depth 6 -Compress
"""
        try:
            completed = subprocess.run(
                [executable, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                check=False,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                return []
            raw = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return []
        result = []
        for item in _list(raw):
            address_items = _list(item.get("addresses"))
            addresses = [entry.get("address") for entry in address_items if entry and entry.get("address")]
            prefixes = [entry.get("prefix") for entry in address_items if entry and entry.get("address")]
            result.append({
                "name": item.get("name"), "index": item.get("index"),
                "description": item.get("description") or item.get("name"),
                "kind": _kind(item.get("name", ""), item.get("description", ""), addresses),
                "connected": bool(item.get("connected")), "addresses": addresses,
                "prefixes": prefixes, "gateways": _list(item.get("gateways")),
                "dns_servers": _list(item.get("dns_servers")),
                "mac_address": item.get("mac_address") or None,
                "ssid": item.get("ssid") or None,
            })
        return result

    @staticmethod
    def _windows_ip_helper_interfaces():
        """Use GetAdaptersAddresses without requiring PowerShell or administrator rights."""
        if os.name != "nt":
            return []
        from ctypes import wintypes

        class SocketAddress(ctypes.Structure):
            _fields_ = [("pointer", ctypes.c_void_p), ("length", ctypes.c_int)]

        class UnicastAddress(ctypes.Structure):
            pass

        class DnsAddress(ctypes.Structure):
            pass

        class GatewayAddress(ctypes.Structure):
            pass

        UnicastPointer = ctypes.POINTER(UnicastAddress)
        DnsPointer = ctypes.POINTER(DnsAddress)
        GatewayPointer = ctypes.POINTER(GatewayAddress)
        UnicastAddress._fields_ = [
            ("length", wintypes.ULONG), ("flags", wintypes.DWORD), ("next", UnicastPointer),
            ("address", SocketAddress), ("prefix_origin", ctypes.c_int), ("suffix_origin", ctypes.c_int),
            ("dad_state", ctypes.c_int), ("valid_lifetime", wintypes.ULONG),
            ("preferred_lifetime", wintypes.ULONG), ("lease_lifetime", wintypes.ULONG),
            ("prefix_length", ctypes.c_ubyte),
        ]
        DnsAddress._fields_ = [
            ("length", wintypes.ULONG), ("reserved", wintypes.DWORD),
            ("next", DnsPointer), ("address", SocketAddress),
        ]
        GatewayAddress._fields_ = [
            ("length", wintypes.ULONG), ("reserved", wintypes.DWORD),
            ("next", GatewayPointer), ("address", SocketAddress),
        ]

        class AdapterAddress(ctypes.Structure):
            pass

        AdapterPointer = ctypes.POINTER(AdapterAddress)
        AdapterAddress._fields_ = [
            ("length", wintypes.ULONG), ("if_index", wintypes.DWORD), ("next", AdapterPointer),
            ("adapter_name", ctypes.c_char_p), ("first_unicast", UnicastPointer),
            ("first_anycast", ctypes.c_void_p), ("first_multicast", ctypes.c_void_p),
            ("first_dns", DnsPointer), ("dns_suffix", wintypes.LPWSTR),
            ("description", wintypes.LPWSTR), ("friendly_name", wintypes.LPWSTR),
            ("physical_address", ctypes.c_ubyte * 8), ("physical_address_length", wintypes.DWORD),
            ("flags", wintypes.DWORD), ("mtu", wintypes.DWORD), ("if_type", wintypes.DWORD),
            ("oper_status", ctypes.c_int), ("ipv6_if_index", wintypes.DWORD),
            ("zone_indices", wintypes.DWORD * 16), ("first_prefix", ctypes.c_void_p),
            ("transmit_link_speed", ctypes.c_ulonglong), ("receive_link_speed", ctypes.c_ulonglong),
            ("first_wins", ctypes.c_void_p), ("first_gateway", GatewayPointer),
        ]

        def address_text(value):
            if not value.pointer or value.length < 2:
                return None
            family = ctypes.c_ushort.from_address(value.pointer).value
            raw = ctypes.string_at(value.pointer, value.length)
            try:
                if family == socket.AF_INET and len(raw) >= 8:
                    return socket.inet_ntop(socket.AF_INET, raw[4:8])
                if family == socket.AF_INET6 and len(raw) >= 24:
                    return socket.inet_ntop(socket.AF_INET6, raw[8:24])
            except (OSError, ValueError):
                return None
            return None

        size = wintypes.ULONG(15_000)
        flags = 0x0010 | 0x0080
        api = ctypes.windll.iphlpapi.GetAdaptersAddresses
        for _ in range(3):
            buffer = ctypes.create_string_buffer(size.value)
            result = api(0, flags, None, buffer, ctypes.byref(size))
            if result != 111:
                break
        if result != 0:
            return []
        interfaces = []
        current = ctypes.cast(buffer, AdapterPointer)
        while current:
            adapter = current.contents
            addresses, prefixes = [], []
            unicast = adapter.first_unicast
            while unicast:
                text = address_text(unicast.contents.address)
                if text:
                    addresses.append(text); prefixes.append(int(unicast.contents.prefix_length))
                unicast = unicast.contents.next
            dns_servers = []
            dns = adapter.first_dns
            while dns:
                text = address_text(dns.contents.address)
                if text:
                    dns_servers.append(text)
                dns = dns.contents.next
            gateways = []
            gateway = adapter.first_gateway
            while gateway:
                text = address_text(gateway.contents.address)
                if text:
                    gateways.append(text)
                gateway = gateway.contents.next
            length = min(int(adapter.physical_address_length), len(adapter.physical_address))
            mac = ":".join(f"{adapter.physical_address[index]:02x}" for index in range(length)) or None
            name = adapter.friendly_name or (adapter.adapter_name.decode(errors="replace") if adapter.adapter_name else "")
            description = adapter.description or name
            if "bluetooth" in f"{name} {description}".casefold():
                kind = "other"
            elif adapter.if_type == 71:
                kind = "wifi"
            elif adapter.if_type == 24:
                kind = "loopback"
            elif adapter.if_type == 6:
                kind = "ethernet"
            else:
                kind = _kind(name, description, addresses)
            interfaces.append({
                "name": name, "index": int(adapter.if_index), "description": description,
                "kind": kind, "connected": adapter.oper_status == 1,
                "addresses": addresses, "prefixes": prefixes, "gateways": gateways,
                "dns_servers": dns_servers, "mac_address": mac,
            })
            current = adapter.next
        return interfaces

    @staticmethod
    def _linux_interfaces():
        executable = shutil.which("ip")
        if executable is None:
            return []
        try:
            addresses_run = subprocess.run([executable, "-j", "address", "show"], capture_output=True, text=True, timeout=10, check=False)
            routes_run = subprocess.run([executable, "-j", "route", "show", "default"], capture_output=True, text=True, timeout=10, check=False)
            if addresses_run.returncode != 0:
                return []
            address_data = json.loads(addresses_run.stdout)
            route_data = json.loads(routes_run.stdout) if routes_run.returncode == 0 and routes_run.stdout.strip() else []
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return []
        gateways = {}
        for route in route_data:
            if route.get("dev") and route.get("gateway"):
                gateways.setdefault(route["dev"], []).append(route["gateway"])
        dns = _dns_from_resolv_conf()
        result = []
        for item in address_data:
            details = [entry for entry in item.get("addr_info", []) if entry.get("local")]
            values = [entry["local"] for entry in details]
            result.append({
                "name": item.get("ifname"), "index": item.get("ifindex"),
                "description": item.get("ifname"),
                "kind": _kind(item.get("ifname", ""), addresses=values),
                "connected": "UP" in item.get("flags", []),
                "addresses": values, "prefixes": [entry.get("prefixlen") for entry in details],
                "gateways": gateways.get(item.get("ifname"), []), "dns_servers": dns,
                "mac_address": item.get("address") or None,
            })
        return result

    def wifi_scan(self, interface_name):
        if platform.system().casefold() != "linux" or shutil.which("nmcli") is None:
            raise NotImplementedError("Native Wi-Fi scanning requires NetworkManager/nmcli on Linux or a host adapter.")
        completed = subprocess.run(
            ["nmcli", "--terse", "--escape", "no", "--separator", "|", "--fields", "SSID,SIGNAL,CHAN,BSSID,SECURITY", "device", "wifi", "list", "ifname", interface_name],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "nmcli Wi-Fi scan failed")
        result = []
        for line in completed.stdout.splitlines():
            parts = line.split("|", 4)
            if len(parts) != 5 or not parts[0]:
                continue
            signal = int(parts[1]) if parts[1].isdigit() else None
            channel = int(parts[2]) if parts[2].isdigit() else None
            result.append({"ssid": parts[0], "signal_strength": signal, "channel": channel,
                           "bssid": parts[3] or None, "security": parts[4] or "open"})
        return result


def _ip(value, name, position, runtime):
    if isinstance(value, IpAddressValue):
        return value
    if type(value) is not str:
        runtime.type_error(position, "ip_address or string", runtime.type_name(value), f"{name} requires an IP address or string.")
    try:
        return IpAddressValue(ipaddress.ip_address(value.split("%", 1)[0]))
    except ValueError:
        raise error("E970", "Invalid IP address", f"{name} requires a valid IPv4 or IPv6 address.", position, actual=repr(value))


def _optional_ip(value):
    if not value:
        return None
    try:
        return IpAddressValue(ipaddress.ip_address(str(value).split("%", 1)[0]))
    except ValueError:
        return None


def _prefix_mask(address, prefix):
    if address is None or prefix is None:
        return None
    try:
        parsed = ipaddress.ip_address(str(address).split("%", 1)[0])
        network = ipaddress.ip_network(f"{parsed}/{int(prefix)}", strict=False)
        return IpAddressValue(network.netmask)
    except (ValueError, TypeError):
        return None


def _interface_value(item):
    if isinstance(item, NetworkInterfaceValue):
        return item
    addresses = [value for value in (_optional_ip(item) for item in item.get("addresses", [])) if value is not None]
    gateways = [value for value in (_optional_ip(item) for item in item.get("gateways", [])) if value is not None]
    dns = [value for value in (_optional_ip(item) for item in item.get("dns_servers", [])) if value is not None]
    primary_index = next((index for index, value in enumerate(addresses) if value.value.version == 4 and not value.value.is_loopback), 0 if addresses else None)
    primary = None if primary_index is None else addresses[primary_index]
    prefixes = item.get("prefixes", [])
    prefix = None if primary_index is None or primary_index >= len(prefixes) else prefixes[primary_index]
    mac = item.get("mac_address")
    if mac:
        mac = str(mac).replace("-", ":").casefold()
    return NetworkInterfaceValue.create({
        "name": str(item.get("name") or ""), "index": int(item.get("index") or 0),
        "description": str(item.get("description") or item.get("name") or ""),
        "kind": str(item.get("kind") or "other"), "connected": bool(item.get("connected")),
        "addresses": addresses, "ip_address": primary,
        "gateway": gateways[0] if gateways else None,
        "subnet_mask": _prefix_mask(None if primary is None else primary.value, prefix),
        "dns_servers": dns, "mac_address": mac,
        "ssid": item.get("ssid"), "bssid": item.get("bssid"),
        "channel": item.get("channel"), "signal_strength": item.get("signal_strength"),
    })


def _inspect(runtime, position):
    runtime.capabilities.require(runtime.capabilities.inspect_network, "inspect network interfaces", position)


def _interfaces(runtime, position):
    _inspect(runtime, position)
    try:
        values = [_interface_value(value) for value in runtime.network_adapter.interfaces()]
    except Exception as exc:
        raise error("E972", "network_interface_error", str(exc), position)
    return sorted(values, key=lambda value: value.fields["name"].casefold())


def _require_interface(value, name, position, runtime, kind=None, refresh=True):
    if not isinstance(value, NetworkInterfaceValue):
        runtime.type_error(position, "network_interface", runtime.type_name(value), f"{name}() requires a network interface.")
    current = value
    if refresh:
        current = next((item for item in _interfaces(runtime, position) if item.fields["name"] == value.fields["name"]), None)
        if current is None:
            raise error("E972", "network_interface_error", "The selected network interface no longer exists.", position, actual=value.fields["name"])
    if kind is not None and current.fields["kind"] != kind:
        raise error("E972", "network_interface_error", f"{name}() requires a {kind} interface.", position,
                    expected=kind, actual=current.fields["kind"])
    return current


def _network_interfaces(args, named, position, runtime):
    return _interfaces(runtime, position)


def _network_interface(args, named, position, runtime):
    name = args[0]
    if type(name) is not str or not name:
        runtime.type_error(position, "non-empty interface name", runtime.type_name(name), "network_interface() requires an interface name.")
    found = next((item for item in _interfaces(runtime, position) if item.fields["name"] == name), None)
    if found is None:
        raise error("E972", "network_interface_error", "No network interface has the requested name.", position, actual=name)
    return found


def _interface_field(field, function_name):
    def implementation(args, named, position, runtime):
        return _require_interface(args[0], function_name, position, runtime).fields[field]
    return implementation


def _network_status(args, named, position, runtime):
    value = _require_interface(args[0], "network_status", position, runtime)
    return ObjectValue.create({key: value.fields[key] for key in (
        "name", "kind", "connected", "ip_address", "gateway", "subnet_mask", "dns_servers", "mac_address"
    )})


def _kind_status(kind, function_name):
    def implementation(args, named, position, runtime):
        value = _require_interface(args[0], function_name, position, runtime, kind)
        return ObjectValue.create({key: value.fields[key] for key in (
            "name", "kind", "connected", "ip_address", "gateway", "subnet_mask", "dns_servers", "mac_address"
        )})
    return implementation


def _open_kind(kind, function_name):
    def implementation(args, named, position, runtime):
        name = args[0] if args else None
        if name is not None and (type(name) is not str or not name):
            runtime.type_error(position, "non-empty interface name", runtime.type_name(name), f"{function_name}() name must be a string.")
        candidates = [item for item in _interfaces(runtime, position) if item.fields["kind"] == kind and (name is None or item.fields["name"] == name)]
        if not candidates:
            raise error("E972", "network_interface_error", f"No {kind} network interface is available.", position, actual=name or kind)
        return candidates[0]
    return implementation


def _wifi_field(field, name):
    def implementation(args, named, position, runtime):
        return _require_interface(args[0], name, position, runtime, "wifi").fields[field]
    return implementation


def _wifi_scan(args, named, position, runtime):
    interface = _require_interface(args[0], "wifi_scan", position, runtime, "wifi")
    try:
        records = runtime.network_adapter.wifi_scan(interface.fields["name"])
    except NotImplementedError as exc:
        raise error("E978", "network_operation_unavailable", str(exc), position, actual="wifi_scan")
    except Exception as exc:
        raise error("E973", "network_connection_error", str(exc), position, actual="wifi_scan")
    result = []
    for record in records:
        ssid = record.get("ssid")
        if type(ssid) is not str or not ssid:
            continue
        result.append(ObjectValue.create({
            "ssid": ssid, "signal_strength": record.get("signal_strength"),
            "channel": record.get("channel"), "bssid": record.get("bssid"),
            "security": record.get("security") or "unknown",
        }))
    return sorted(result, key=lambda value: (-int(value.fields["signal_strength"] or -1), value.fields["ssid"].casefold()))


def _wifi_wait(args, named, position, runtime):
    interface = _require_interface(args[0], "wifi_wait_until_connected", position, runtime, "wifi", refresh=False)
    timeout = args[1]
    if not isinstance(timeout, DurationValue) or timeout.milliseconds < 0 or timeout.milliseconds > runtime.capabilities.max_socket_timeout_ms:
        raise error("E974", "network_timeout_error", "Wi-Fi wait timeout must be a non-negative duration within the host limit.", position)
    deadline = time.monotonic() + timeout.milliseconds / 1000
    while True:
        if _require_interface(interface, "wifi_wait_until_connected", position, runtime, "wifi").fields["connected"]:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))


def _network_set_preferred(args, named, position, runtime):
    names = args[0]
    if type(names) is not list or not names or any(type(value) is not str or not value for value in names):
        runtime.type_error(position, "non-empty list<string>", runtime.type_name(names), "network_set_preferred_interfaces() requires interface names.")
    if len(names) != len(set(names)):
        raise error("E972", "network_interface_error", "Preferred interface names must be unique.", position)
    available = {item.fields["name"] for item in _interfaces(runtime, position)}
    missing = [name for name in names if name not in available]
    if missing:
        raise error("E972", "network_interface_error", "A preferred interface does not exist.", position, actual=missing[0])
    runtime.network_preferred_interfaces = list(names)
    return None


def _network_preferred(args, named, position, runtime):
    values = _interfaces(runtime, position)
    by_name = {value.fields["name"]: value for value in values}
    order = runtime.network_preferred_interfaces or [value.fields["name"] for value in values]
    return next((by_name[name] for name in order if name in by_name and by_name[name].fields["connected"]), None)


def _ip_address(args, named, position, runtime):
    return _ip(args[0], "ip_address()", position, runtime)


def _ip_field(name):
    def implementation(args, named, position, runtime):
        value = _ip(args[0], f"ip_address_{name}()", position, runtime).value
        if name == "version":
            return value.version
        return bool(getattr(value, f"is_{name}"))
    return implementation


def _host_text(value, name, position, runtime):
    if isinstance(value, IpAddressValue):
        return str(value.value)
    if type(value) is not str or not value or "\0" in value or len(value) > 253:
        runtime.type_error(position, "safe hostname or ip_address", runtime.type_name(value), f"{name} requires a safe hostname or IP address.")
    return value.casefold().rstrip(".")


def _port(value, name, position, runtime, allow_zero=False):
    minimum = 0 if allow_zero else 1
    if type(value) is not int or not minimum <= value <= 65_535:
        runtime.type_error(position, f"integer port {minimum}..65535", runtime.type_name(value), f"{name} port is outside the valid range.")
    return value


def _require_host_allowed(host, position, runtime):
    capability = runtime.capabilities
    capability.require(capability.network, "access network", position)
    if capability.network_hosts is not None and not any(host == allowed.casefold().rstrip(".") or host.endswith("." + allowed.casefold().rstrip(".")) for allowed in capability.network_hosts):
        raise error("E979", "Permission error", "Network host is outside the host capability allowlist.", position, actual=host)


def _resolve(host_value, port, position, runtime, socket_type=socket.SOCK_STREAM):
    host = _host_text(host_value, "network operation", position, runtime)
    _require_host_allowed(host, position, runtime)
    if port is not None:
        port = _port(port, "network operation", position, runtime)
        allowed_ports = runtime.capabilities.network_ports
        if allowed_ports is not None and port not in allowed_ports:
            raise error("E979", "Permission error", "Network port is outside the host capability allowlist.", position, actual=str(port))
    try:
        records = socket.getaddrinfo(host, port, type=socket_type)
    except socket.gaierror as exc:
        raise error("E971", "network_dns_error", str(exc), position, actual=host)
    result, seen = [], set()
    for family, kind, protocol, _, address in records:
        ip = ipaddress.ip_address(address[0].split("%", 1)[0])
        if not runtime.capabilities.allow_private_network and not ip.is_global:
            raise error("E979", "Permission error", "Network capability rejects non-public destination addresses.", position, actual=str(ip))
        key = (family, address[0], port)
        if key not in seen:
            seen.add(key); result.append((family, kind, protocol, address))
    return host, result


def _dns_resolve(args, named, position, runtime):
    _, records = _resolve(args[0], None, position, runtime)
    values = []
    for _, _, _, address in records:
        value = _optional_ip(address[0])
        if value is not None and value not in values:
            values.append(value)
    return sorted(values, key=lambda item: (item.value.version, int(item.value)))


def _dns_reverse(args, named, position, runtime):
    value = _ip(args[0], "dns_reverse_lookup()", position, runtime)
    _require_host_allowed(str(value.value), position, runtime)
    if not runtime.capabilities.allow_private_network and not value.value.is_global:
        raise error("E979", "Permission error", "Network capability rejects non-public destination addresses.", position, actual=str(value.value))
    try:
        return socket.gethostbyaddr(str(value.value))[0]
    except (socket.herror, socket.gaierror):
        return None


def _timeout(value, position, runtime):
    if not isinstance(value, DurationValue) or value.milliseconds <= 0 or value.milliseconds > runtime.capabilities.max_socket_timeout_ms:
        raise error("E974", "network_timeout_error", "Socket timeout must be a positive duration within the host limit.", position)
    return value.milliseconds / 1000


def _payload(value, name, position, runtime):
    if isinstance(value, BytesValue):
        return value.value
    if type(value) is str:
        return value.encode("utf-8")
    runtime.type_error(position, "string or bytes", runtime.type_name(value), f"{name} payload must be string or bytes.")


def _receive_limit(value, position, runtime):
    if type(value) is not int or value < 1 or value > runtime.capabilities.max_socket_receive_bytes:
        raise error("E975", "network_limit_error", "Socket receive size must be within the host byte limit.", position,
                    expected=f"1..{runtime.capabilities.max_socket_receive_bytes}", actual=repr(value))
    return value


def _tcp(args, name, position, runtime):
    value = args[0]
    if not isinstance(value, TcpConnectionValue):
        runtime.type_error(position, "tcp_connection", runtime.type_name(value), f"{name}() requires a TCP connection.")
    if value.closed:
        raise error("E976", "network_closed_error", "TCP connection is already closed.", position, actual=f"{value.host}:{value.port}")
    return value


def _tcp_connect(args, named, position, runtime):
    host_value, port = args
    host, records = _resolve(host_value, port, position, runtime)
    timeout = _timeout(named.get("timeout", DEFAULT_TIMEOUT), position, runtime)
    last = None
    for family, kind, protocol, address in records:
        native = socket.socket(family, kind, protocol)
        native.settimeout(timeout)
        try:
            native.connect(address)
            value = TcpConnectionValue(native, host, port)
            runtime.network_resources.append(value)
            return value
        except socket.timeout as exc:
            last = exc; native.close()
        except OSError as exc:
            last = exc; native.close()
    if isinstance(last, socket.timeout):
        raise error("E974", "network_timeout_error", "TCP connection timed out.", position, actual=f"{host}:{port}")
    raise error("E973", "network_connection_error", str(last or "No destination address was available."), position, actual=f"{host}:{port}")


def _tcp_send(args, named, position, runtime):
    connection = _tcp(args, "tcp_send", position, runtime); data = _payload(args[1], "tcp_send", position, runtime)
    try:
        connection.native.sendall(data); return len(data)
    except socket.timeout:
        raise error("E974", "network_timeout_error", "TCP send timed out.", position)
    except OSError as exc:
        raise error("E973", "network_connection_error", str(exc), position)


def _tcp_receive(args, named, position, runtime):
    connection = _tcp(args, "tcp_receive", position, runtime)
    maximum = _receive_limit(args[1] if len(args) > 1 else DEFAULT_RECEIVE_BYTES, position, runtime)
    timeout = named.get("timeout")
    previous = connection.native.gettimeout()
    if timeout is not None:
        connection.native.settimeout(_timeout(timeout, position, runtime))
    try:
        return BytesValue(connection.native.recv(maximum))
    except socket.timeout:
        raise error("E974", "network_timeout_error", "TCP receive timed out.", position)
    except OSError as exc:
        raise error("E973", "network_connection_error", str(exc), position)
    finally:
        if timeout is not None and not connection.closed:
            connection.native.settimeout(previous)


def _tcp_close(args, named, position, runtime):
    value = args[0]
    if not isinstance(value, TcpConnectionValue):
        runtime.type_error(position, "tcp_connection", runtime.type_name(value), "tcp_close() requires a TCP connection.")
    if not value.closed:
        try:
            value.native.close()
        finally:
            value.closed = True
    return None


def _udp(args, name, position, runtime):
    value = args[0]
    if not isinstance(value, UdpSocketValue):
        runtime.type_error(position, "udp_socket", runtime.type_name(value), f"{name}() requires a UDP socket.")
    if value.closed:
        raise error("E976", "network_closed_error", "UDP socket is already closed.", position)
    return value


def _udp_open(args, named, position, runtime):
    runtime.capabilities.require(runtime.capabilities.network, "access network", position)
    local_address = named.get("local_address")
    local_port = named.get("local_port")
    timeout = _timeout(named.get("timeout", DEFAULT_TIMEOUT), position, runtime)
    if (local_address is None) != (local_port is None):
        raise error("E977", "network_protocol_error", "udp_open() requires both local_address and local_port when binding.", position)
    native = socket.socket(socket.AF_INET6 if local_address and ":" in _host_text(local_address, "udp_open()", position, runtime) else socket.AF_INET, socket.SOCK_DGRAM)
    native.settimeout(timeout)
    try:
        if local_address is not None:
            runtime.capabilities.require(runtime.capabilities.bind_network, "bind a network socket", position)
            address = _host_text(local_address, "udp_open()", position, runtime)
            port = _port(local_port, "udp_open()", position, runtime, allow_zero=True)
            if runtime.capabilities.network_bind_hosts is not None and address not in runtime.capabilities.network_bind_hosts:
                raise error("E979", "Permission error", "UDP bind address is outside the host capability allowlist.", position, actual=address)
            if runtime.capabilities.network_bind_ports is not None and port not in runtime.capabilities.network_bind_ports:
                raise error("E979", "Permission error", "UDP bind port is outside the host capability allowlist.", position, actual=str(port))
            native.bind((address, port)); actual = native.getsockname()
            local_address, local_port = actual[0], actual[1]
        value = UdpSocketValue(native, local_address, local_port)
        runtime.network_resources.append(value)
        return value
    except Exception:
        native.close(); raise


def _udp_send(args, named, position, runtime):
    value = _udp(args, "udp_send", position, runtime); host_value, port, payload = args[1:]
    host, records = _resolve(host_value, port, position, runtime, socket.SOCK_DGRAM)
    data = _payload(payload, "udp_send", position, runtime)
    family, _, _, address = next((record for record in records if record[0] == value.native.family), records[0])
    if family != value.native.family:
        raise error("E977", "network_protocol_error", "UDP destination address family does not match the socket.", position, actual=host)
    try:
        return value.native.sendto(data, address)
    except socket.timeout:
        raise error("E974", "network_timeout_error", "UDP send timed out.", position)
    except OSError as exc:
        raise error("E973", "network_connection_error", str(exc), position)


def _udp_receive(args, named, position, runtime):
    value = _udp(args, "udp_receive", position, runtime)
    maximum = _receive_limit(args[1] if len(args) > 1 else DEFAULT_RECEIVE_BYTES, position, runtime)
    timeout = named.get("timeout")
    previous = value.native.gettimeout()
    if timeout is not None:
        value.native.settimeout(_timeout(timeout, position, runtime))
    try:
        data, address = value.native.recvfrom(maximum)
        return ObjectValue.create({"data": BytesValue(data), "address": _optional_ip(address[0]), "port": int(address[1])})
    except socket.timeout:
        raise error("E974", "network_timeout_error", "UDP receive timed out.", position)
    except OSError as exc:
        raise error("E973", "network_connection_error", str(exc), position)
    finally:
        if timeout is not None and not value.closed:
            value.native.settimeout(previous)


def _udp_close(args, named, position, runtime):
    value = args[0]
    if not isinstance(value, UdpSocketValue):
        runtime.type_error(position, "udp_socket", runtime.type_name(value), "udp_close() requires a UDP socket.")
    if not value.closed:
        try:
            value.native.close()
        finally:
            value.closed = True
    return None


NETWORK_BUILTINS = (
    UtilityFunction("ip_address", 1, 1, _ip_address),
    UtilityFunction("ip_address_version", 1, 1, _ip_field("version")),
    UtilityFunction("ip_address_is_private", 1, 1, _ip_field("private")),
    UtilityFunction("ip_address_is_loopback", 1, 1, _ip_field("loopback")),
    UtilityFunction("ip_address_is_global", 1, 1, _ip_field("global")),
    UtilityFunction("network_interfaces", 0, 0, _network_interfaces),
    UtilityFunction("network_interface", 1, 1, _network_interface),
    UtilityFunction("network_status", 1, 1, _network_status),
    UtilityFunction("network_is_connected", 1, 1, _interface_field("connected", "network_is_connected")),
    UtilityFunction("network_ip_address", 1, 1, _interface_field("ip_address", "network_ip_address")),
    UtilityFunction("network_ip_addresses", 1, 1, _interface_field("addresses", "network_ip_addresses")),
    UtilityFunction("network_gateway", 1, 1, _interface_field("gateway", "network_gateway")),
    UtilityFunction("network_subnet_mask", 1, 1, _interface_field("subnet_mask", "network_subnet_mask")),
    UtilityFunction("network_dns_servers", 1, 1, _interface_field("dns_servers", "network_dns_servers")),
    UtilityFunction("network_mac_address", 1, 1, _interface_field("mac_address", "network_mac_address")),
    UtilityFunction("network_hostname", 0, 0, lambda args, named, position, runtime: socket.gethostname()),
    UtilityFunction("network_set_preferred_interfaces", 1, 1, _network_set_preferred),
    UtilityFunction("network_preferred_interface", 0, 0, _network_preferred),
    UtilityFunction("ethernet_open", 0, 1, _open_kind("ethernet", "ethernet_open")),
    UtilityFunction("ethernet_status", 1, 1, _kind_status("ethernet", "ethernet_status")),
    UtilityFunction("wifi_open", 0, 1, _open_kind("wifi", "wifi_open")),
    UtilityFunction("wifi_scan", 1, 1, _wifi_scan),
    UtilityFunction("wifi_status", 1, 1, _kind_status("wifi", "wifi_status")),
    UtilityFunction("wifi_is_connected", 1, 1, _wifi_field("connected", "wifi_is_connected")),
    UtilityFunction("wifi_ssid", 1, 1, _wifi_field("ssid", "wifi_ssid")),
    UtilityFunction("wifi_bssid", 1, 1, _wifi_field("bssid", "wifi_bssid")),
    UtilityFunction("wifi_channel", 1, 1, _wifi_field("channel", "wifi_channel")),
    UtilityFunction("wifi_signal_strength", 1, 1, _wifi_field("signal_strength", "wifi_signal_strength")),
    UtilityFunction("wifi_wait_until_connected", 2, 2, _wifi_wait),
    UtilityFunction("dns_resolve", 1, 1, _dns_resolve),
    UtilityFunction("dns_reverse_lookup", 1, 1, _dns_reverse),
    UtilityFunction("tcp_connect", 2, 2, _tcp_connect, ("timeout",)),
    UtilityFunction("tcp_send", 2, 2, _tcp_send),
    UtilityFunction("tcp_receive", 1, 2, _tcp_receive, ("timeout",)),
    UtilityFunction("tcp_close", 1, 1, _tcp_close),
    UtilityFunction("udp_open", 0, 0, _udp_open, ("local_address", "local_port", "timeout")),
    UtilityFunction("udp_send", 4, 4, _udp_send),
    UtilityFunction("udp_receive", 1, 2, _udp_receive, ("timeout",)),
    UtilityFunction("udp_close", 1, 1, _udp_close),
)
