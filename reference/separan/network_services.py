"""Capability-gated Wi-Fi AP, DHCP server, and simple DNS server APIs."""

from dataclasses import dataclass
import ipaddress
import re

from .auth import SecretValue
from .errors import error
from .network import IpAddressValue, _adapter_call, _require_interface
from .objects import ObjectValue
from .system_utilities import UtilityFunction
from .temporal import DurationValue, TimezoneValue, UTC, from_unix_milliseconds


SERVICE_STATES = frozenset({"starting", "running", "stopping", "stopped", "failed"})
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")
DNS_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


@dataclass
class WifiAccessPointResource:
    adapter: object
    interface_name: str
    closed: bool = False

    def close(self):
        if not self.closed:
            self.adapter.wifi_stop_access_point(self.interface_name)
            self.closed = True


@dataclass
class DhcpServerValue:
    native: object
    adapter: object
    interface_name: str
    configuration: dict
    closed: bool = False

    def close(self):
        if not self.closed:
            self.adapter.dhcp_server_stop(self.native)
            self.closed = True


@dataclass
class DnsServerValue:
    native: object
    adapter: object
    interface_name: str
    configuration: dict
    closed: bool = False

    def close(self):
        if not self.closed:
            self.adapter.dns_server_stop(self.native)
            self.closed = True


def _hosting_interface(value, function_name, position, runtime, kind=None, configure=False):
    runtime.capabilities.require(runtime.capabilities.host_network_services, "host local network services", position)
    if configure:
        runtime.capabilities.require(runtime.capabilities.configure_network, "configure network interfaces", position)
    return _require_interface(value, function_name, position, runtime, kind)


def _service_adapter(runtime, method_name, interface, position, *arguments, category="network_service_error"):
    code = {"network_service_error": "E981", "dhcp_server_error": "E982", "dns_server_error": "E983",
            "wifi_access_point_error": "E984"}[category]
    return _adapter_call(runtime, method_name, interface, position, *arguments,
                         error_code=code, error_category=category)


def _required(named, names, function_name, position):
    missing = [name for name in names if name not in named]
    if missing:
        raise error("E207", "Missing named argument", f"{function_name}() requires named argument '{missing[0]}'.", position,
                    expected=missing[0])


def _ipv4(value, field, position, runtime, code="E982", category="dhcp_server_error"):
    if hasattr(value, "value") and isinstance(value.value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        address = value.value
    elif type(value) is str:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise error(code, category, f"{field} must be a valid IPv4 address.", position, actual=value)
    else:
        runtime.type_error(position, "IPv4 address string or ip_address", runtime.type_name(value), f"{field} requires an IPv4 address.")
    if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_loopback:
        raise error(code, category, f"{field} requires a non-loopback unicast IPv4 address.", position, actual=str(address))
    return address


def _prefix(value, position):
    if type(value) is not int or not 1 <= value <= 30:
        raise error("E982", "dhcp_server_error", "DHCP server prefix must be an integer from 1 through 30.", position, actual=repr(value))
    return value


def _duration(value, position, runtime):
    if not isinstance(value, DurationValue):
        runtime.type_error(position, "duration", runtime.type_name(value), "DHCP lease_time must be a duration.")
    if not 60_000 <= value.milliseconds <= 604_800_000:
        raise error("E982", "dhcp_server_error", "DHCP lease_time must be from 1 minute through 7 days.", position)
    return value.milliseconds


def _mac(value, position):
    if type(value) is not str or MAC_RE.fullmatch(value) is None:
        raise error("E982", "dhcp_server_error", "DHCP reservation keys must be colon-separated MAC addresses.", position, actual=repr(value))
    return value.upper()


def _reservations(value, network, in_dynamic_pool, reserved_addresses, position, runtime):
    if value is None:
        return {}
    if not isinstance(value, ObjectValue):
        runtime.type_error(position, "object or null", runtime.type_name(value), "DHCP reservations must be an object of MAC-to-IPv4 mappings.")
    result = {}
    used = set(reserved_addresses)
    for key, raw_address in value.fields.items():
        mac = _mac(key, position)
        address = _ipv4(raw_address, "DHCP reservation address", position, runtime)
        if address not in network or address in (network.network_address, network.broadcast_address):
            raise error("E982", "dhcp_server_error", "DHCP reservation address must be a usable address in the server subnet.", position, actual=str(address))
        if in_dynamic_pool(address):
            raise error("E982", "dhcp_server_error", "DHCP reservation address must be outside the dynamic pool.", position, actual=str(address))
        if address in used:
            raise error("E982", "dhcp_server_error", "DHCP reservation addresses must be unique and cannot use the server or gateway address.", position, actual=str(address))
        used.add(address)
        result[mac] = str(address)
    return result


def _wifi_start_access_point(args, named, position, runtime):
    interface = _hosting_interface(args[0], "wifi_start_access_point", position, runtime, "wifi", configure=True)
    if any(isinstance(resource, WifiAccessPointResource) and not resource.closed and resource.interface_name == interface.fields["name"]
           for resource in runtime.network_resources):
        raise error("E984", "wifi_access_point_error", "A Wi-Fi access point is already running on this interface.", position,
                    actual=interface.fields["name"])
    _required(named, ("ssid", "password"), "wifi_start_access_point", position)
    ssid = named["ssid"]
    if type(ssid) is not str or not 1 <= len(ssid.encode("utf-8")) <= 32 or any(ord(char) < 32 for char in ssid):
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP ssid must contain 1 through 32 UTF-8 bytes without control characters.", position)
    password = named["password"]
    if not isinstance(password, SecretValue):
        runtime.type_error(position, "secret", runtime.type_name(password), "Wi-Fi AP password must use the secret type.")
    if not 8 <= len(password.value) <= 63:
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP password must contain 8 through 63 bytes.", position)
    try:
        password_text = password.value.decode("utf-8")
    except UnicodeDecodeError:
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP password must be valid UTF-8.", position)
    if any(ord(char) < 32 or ord(char) == 127 for char in password_text):
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP password cannot contain control characters.", position)
    channel = named.get("channel", 6)
    if type(channel) is not int or not 1 <= channel <= 14:
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP channel must be an integer from 1 through 14.", position, actual=repr(channel))
    configuration = {"ssid": ssid, "password": password.value, "channel": channel, "security": "wpa2_personal"}
    _service_adapter(runtime, "wifi_start_access_point", interface, position, configuration, category="wifi_access_point_error")
    runtime.network_resources.append(WifiAccessPointResource(runtime.network_adapter, interface.fields["name"]))
    return None


def _wifi_stop_access_point(args, named, position, runtime):
    interface = _hosting_interface(args[0], "wifi_stop_access_point", position, runtime, "wifi", configure=True)
    _service_adapter(runtime, "wifi_stop_access_point", interface, position, category="wifi_access_point_error")
    for resource in runtime.network_resources:
        if isinstance(resource, WifiAccessPointResource) and resource.interface_name == interface.fields["name"]:
            resource.closed = True
    return None


def _wifi_access_point_status(args, named, position, runtime):
    interface = _hosting_interface(args[0], "wifi_access_point_status", position, runtime, "wifi")
    raw = _service_adapter(runtime, "wifi_access_point_status", interface, position, category="wifi_access_point_error")
    if not isinstance(raw, dict):
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP adapter status must be an object-shaped record.", position)
    state = raw.get("state")
    client_count = raw.get("client_count", 0)
    ssid = raw.get("ssid")
    channel = raw.get("channel")
    if (state not in SERVICE_STATES or type(client_count) is not int or client_count < 0 or
            (ssid is not None and type(ssid) is not str) or
            (channel is not None and (type(channel) is not int or not 1 <= channel <= 14))):
        raise error("E984", "wifi_access_point_error", "Wi-Fi AP adapter returned invalid status metadata.", position)
    return ObjectValue.create({"state": state, "ssid": ssid, "channel": channel, "client_count": client_count})


def _dhcp_start(args, named, position, runtime):
    interface = _hosting_interface(args[0], "dhcp_server_start", position, runtime)
    _required(named, ("server_address", "prefix", "pool_start", "pool_end", "lease_time"), "dhcp_server_start", position)
    server = _ipv4(named["server_address"], "DHCP server_address", position, runtime)
    prefix = _prefix(named["prefix"], position)
    subnet = ipaddress.ip_network(f"{server}/{prefix}", strict=False)
    pool_start = _ipv4(named["pool_start"], "DHCP pool_start", position, runtime)
    pool_end = _ipv4(named["pool_end"], "DHCP pool_end", position, runtime)
    if pool_start not in subnet or pool_end not in subnet or pool_start in (subnet.network_address, subnet.broadcast_address) or pool_end in (subnet.network_address, subnet.broadcast_address):
        raise error("E982", "dhcp_server_error", "DHCP pool must contain usable IPv4 addresses in the server subnet.", position)
    if int(pool_start) > int(pool_end):
        raise error("E982", "dhcp_server_error", "DHCP pool_start must not be greater than pool_end.", position)
    pool_size = int(pool_end) - int(pool_start) + 1
    if pool_size > runtime.capabilities.max_dhcp_server_leases:
        raise error("E975", "network_limit_error", "DHCP pool exceeds the host lease limit.", position,
                    expected=str(runtime.capabilities.max_dhcp_server_leases), actual=str(pool_size))
    def in_pool(address): return int(pool_start) <= int(address) <= int(pool_end)
    if in_pool(server):
        raise error("E982", "dhcp_server_error", "DHCP server_address must be outside the dynamic pool.", position, actual=str(server))
    gateway = _ipv4(named.get("gateway", str(server)), "DHCP gateway", position, runtime)
    if gateway not in subnet or gateway in (subnet.network_address, subnet.broadcast_address) or in_pool(gateway):
        raise error("E982", "dhcp_server_error", "DHCP gateway must be a usable subnet address outside the dynamic pool.", position, actual=str(gateway))
    dns_raw = named.get("dns_servers", [])
    if type(dns_raw) is not list:
        runtime.type_error(position, "list<IPv4 address>", runtime.type_name(dns_raw), "DHCP dns_servers must be a list.")
    dns = [str(_ipv4(value, "DHCP DNS server", position, runtime)) for value in dns_raw]
    if len(dns) != len(set(dns)):
        raise error("E982", "dhcp_server_error", "DHCP DNS server addresses must be unique.", position)
    reservations = _reservations(named.get("reservations"), subnet, in_pool, {server, gateway}, position, runtime)
    configuration = {
        "server_address": str(server), "prefix": prefix, "pool_start": str(pool_start), "pool_end": str(pool_end),
        "gateway": str(gateway), "dns_servers": dns, "lease_time_ms": _duration(named["lease_time"], position, runtime),
        "reservations": reservations,
    }
    native = _service_adapter(runtime, "dhcp_server_start", interface, position, configuration, category="dhcp_server_error")
    value = DhcpServerValue(native, runtime.network_adapter, interface.fields["name"], configuration)
    runtime.network_resources.append(value)
    return value


def _require_dhcp(value, position, runtime):
    if not isinstance(value, DhcpServerValue):
        runtime.type_error(position, "dhcp_server", runtime.type_name(value), "DHCP server operation requires a DHCP server handle.")
    return value


def _service_state(value, method_name, position, runtime, category):
    if value.closed:
        return "stopped"
    try:
        state = getattr(value.adapter, method_name)(value.native)
    except NotImplementedError as exc:
        raise error("E978", "network_operation_unavailable", str(exc), position, actual=method_name)
    except Exception as exc:
        code = {"dhcp_server_error": "E982", "dns_server_error": "E983"}.get(category, "E981")
        raise error(code, category, str(exc), position, actual=method_name)
    if state not in SERVICE_STATES:
        code = {"dhcp_server_error": "E982", "dns_server_error": "E983"}.get(category, "E981")
        raise error(code, category, "Network service adapter returned an invalid state.", position, actual=repr(state))
    return state


def _dhcp_stop(args, named, position, runtime):
    value = _require_dhcp(args[0], position, runtime)
    runtime.capabilities.require(runtime.capabilities.host_network_services, "host local network services", position)
    try:
        value.close()
    except NotImplementedError as exc:
        raise error("E978", "network_operation_unavailable", str(exc), position, actual="dhcp_server_stop")
    except Exception as exc:
        raise error("E982", "dhcp_server_error", str(exc), position, actual="dhcp_server_stop")
    return None


def _dhcp_status(args, named, position, runtime):
    value = _require_dhcp(args[0], position, runtime)
    runtime.capabilities.require(runtime.capabilities.host_network_services, "host local network services", position)
    return _service_state(value, "dhcp_server_status", position, runtime, "dhcp_server_error")


def _dhcp_leases(args, named, position, runtime):
    value = _require_dhcp(args[0], position, runtime)
    runtime.capabilities.require(runtime.capabilities.host_network_services, "host local network services", position)
    if value.closed:
        raise error("E982", "dhcp_server_error", "Cannot inspect leases on a stopped DHCP server.", position)
    try:
        raw = value.adapter.dhcp_server_leases(value.native)
    except NotImplementedError as exc:
        raise error("E978", "network_operation_unavailable", str(exc), position, actual="dhcp_server_leases")
    except Exception as exc:
        raise error("E982", "dhcp_server_error", str(exc), position, actual="dhcp_server_leases")
    if type(raw) is not list:
        raise error("E982", "dhcp_server_error", "DHCP lease adapter result must be a list.", position)
    result = []
    addresses = set()
    mac_addresses = set()
    subnet = ipaddress.ip_network(f"{value.configuration['server_address']}/{value.configuration['prefix']}", strict=False)
    pool_start = ipaddress.ip_address(value.configuration["pool_start"])
    pool_end = ipaddress.ip_address(value.configuration["pool_end"])
    reserved = set(value.configuration["reservations"].values())
    for item in raw:
        if not isinstance(item, dict):
            raise error("E982", "dhcp_server_error", "Each DHCP lease must be an object-shaped record.", position)
        address = _ipv4(item.get("address"), "DHCP lease address", position, runtime)
        mac = _mac(item.get("mac_address"), position)
        hostname = item.get("hostname")
        expires = item.get("expires_at_unix_ms")
        if hostname is not None and type(hostname) is not str:
            raise error("E982", "dhcp_server_error", "DHCP lease hostname must be string or null.", position)
        if expires is not None and (type(expires) is not int or expires < 0):
            raise error("E982", "dhcp_server_error", "DHCP lease expiration must be non-negative Unix milliseconds or null.", position)
        address_text = str(address)
        in_pool = int(pool_start) <= int(address) <= int(pool_end)
        if address not in subnet or (not in_pool and address_text not in reserved):
            raise error("E982", "dhcp_server_error", "DHCP adapter returned a lease outside the configured pool and reservations.", position, actual=address_text)
        if address_text in addresses or mac in mac_addresses:
            raise error("E982", "dhcp_server_error", "DHCP adapter returned duplicate lease address or MAC identity.", position)
        addresses.add(address_text); mac_addresses.add(mac)
        expires_at = None if expires is None else from_unix_milliseconds(expires, TimezoneValue("UTC", UTC), position)
        result.append(ObjectValue.create({"address": IpAddressValue(address), "mac_address": mac, "hostname": hostname, "expires_at": expires_at}))
    return sorted(result, key=lambda item: (int(item.fields["address"].value), item.fields["mac_address"]))


def _dns_name(value, position):
    if type(value) is not str:
        raise error("E983", "dns_server_error", "DNS record names must be strings.", position, actual=repr(value))
    name = value.rstrip(".").lower()
    if not name or len(name) > 253 or any(DNS_LABEL_RE.fullmatch(label) is None for label in name.split(".")):
        raise error("E983", "dns_server_error", "DNS record name is not a valid ASCII hostname.", position, actual=value)
    return name


def _dns_start(args, named, position, runtime):
    interface = _hosting_interface(args[0], "dns_server_start", position, runtime)
    _required(named, ("server_address", "records"), "dns_server_start", position)
    server = _ipv4(named["server_address"], "DNS server_address", position, runtime, "E983", "dns_server_error")
    records_raw = named["records"]
    if not isinstance(records_raw, ObjectValue):
        runtime.type_error(position, "object", runtime.type_name(records_raw), "DNS records must be an object of hostname-to-IPv4 mappings.")
    if len(records_raw.fields) > runtime.capabilities.max_dns_server_records:
        raise error("E975", "network_limit_error", "DNS record count exceeds the host limit.", position)
    records = {}
    for raw_name, raw_address in records_raw.fields.items():
        name = _dns_name(raw_name, position)
        if name in records:
            raise error("E983", "dns_server_error", "DNS record names must be unique ignoring case and a trailing dot.", position, actual=raw_name)
        records[name] = str(_ipv4(raw_address, "DNS A record", position, runtime, "E983", "dns_server_error"))
    catch_all = named.get("catch_all", False)
    if type(catch_all) is not bool:
        runtime.type_error(position, "boolean", runtime.type_name(catch_all), "DNS catch_all must be boolean.")
    if not records and not catch_all:
        raise error("E983", "dns_server_error", "DNS server requires at least one record unless catch_all is explicitly enabled.", position)
    configuration = {"server_address": str(server), "records": records, "catch_all": catch_all, "record_type": "A"}
    native = _service_adapter(runtime, "dns_server_start", interface, position, configuration, category="dns_server_error")
    value = DnsServerValue(native, runtime.network_adapter, interface.fields["name"], configuration)
    runtime.network_resources.append(value)
    return value


def _require_dns(value, position, runtime):
    if not isinstance(value, DnsServerValue):
        runtime.type_error(position, "dns_server", runtime.type_name(value), "DNS server operation requires a DNS server handle.")
    return value


def _dns_stop(args, named, position, runtime):
    value = _require_dns(args[0], position, runtime)
    runtime.capabilities.require(runtime.capabilities.host_network_services, "host local network services", position)
    try:
        value.close()
    except NotImplementedError as exc:
        raise error("E978", "network_operation_unavailable", str(exc), position, actual="dns_server_stop")
    except Exception as exc:
        raise error("E983", "dns_server_error", str(exc), position, actual="dns_server_stop")
    return None


def _dns_status(args, named, position, runtime):
    value = _require_dns(args[0], position, runtime)
    runtime.capabilities.require(runtime.capabilities.host_network_services, "host local network services", position)
    return _service_state(value, "dns_server_status", position, runtime, "dns_server_error")


NETWORK_SERVICE_BUILTINS = (
    UtilityFunction("wifi_start_access_point", 1, 1, _wifi_start_access_point, ("ssid", "password", "channel")),
    UtilityFunction("wifi_stop_access_point", 1, 1, _wifi_stop_access_point),
    UtilityFunction("wifi_access_point_status", 1, 1, _wifi_access_point_status),
    UtilityFunction("dhcp_server_start", 1, 1, _dhcp_start,
                    ("server_address", "prefix", "pool_start", "pool_end", "lease_time", "gateway", "dns_servers", "reservations")),
    UtilityFunction("dhcp_server_stop", 1, 1, _dhcp_stop),
    UtilityFunction("dhcp_server_status", 1, 1, _dhcp_status),
    UtilityFunction("dhcp_server_leases", 1, 1, _dhcp_leases),
    UtilityFunction("dns_server_start", 1, 1, _dns_start, ("server_address", "records", "catch_all")),
    UtilityFunction("dns_server_stop", 1, 1, _dns_stop),
    UtilityFunction("dns_server_status", 1, 1, _dns_status),
)
