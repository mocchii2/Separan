import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class FakeNetworkServiceAdapter:
    def __init__(self):
        self.operations = []
        self.ap = {"state": "stopped", "ssid": None, "channel": None, "client_count": 0}
        self.dhcp = {}
        self.dns = {}

    def interfaces(self):
        return [{
            "name": "wifi0", "index": 1, "description": "Test Wi-Fi", "kind": "wifi", "connected": False,
            "addresses": ["192.168.4.1"], "prefixes": [24], "gateways": [], "dns_servers": [],
            "mac_address": "AA-BB-CC-DD-EE-FF", "ssid": None, "bssid": None, "channel": None,
            "signal_strength": None, "address_mode": "static", "dhcp_status": "disabled",
            "dhcp_lease": None, "link_local_fallback": False,
        }]

    def wifi_start_access_point(self, interface_name, configuration):
        self.operations.append(("ap_start", interface_name, configuration))
        self.ap = {"state": "running", "ssid": configuration["ssid"], "channel": configuration["channel"], "client_count": 2}

    def wifi_stop_access_point(self, interface_name):
        self.operations.append(("ap_stop", interface_name))
        self.ap["state"] = "stopped"

    def wifi_access_point_status(self, interface_name):
        return dict(self.ap)

    def dhcp_server_start(self, interface_name, configuration):
        handle = object(); self.dhcp[handle] = "running"
        self.operations.append(("dhcp_start", interface_name, configuration))
        return handle

    def dhcp_server_stop(self, handle):
        self.operations.append(("dhcp_stop", handle)); self.dhcp[handle] = "stopped"

    def dhcp_server_status(self, handle):
        return self.dhcp[handle]

    def dhcp_server_leases(self, handle):
        return [
            {"address": "192.168.4.12", "mac_address": "aa:bb:cc:dd:ee:02", "hostname": None, "expires_at_unix_ms": None},
            {"address": "192.168.4.10", "mac_address": "aa:bb:cc:dd:ee:01", "hostname": "phone", "expires_at_unix_ms": 1_900_000_000_000},
        ]

    def dns_server_start(self, interface_name, configuration):
        handle = object(); self.dns[handle] = "running"
        self.operations.append(("dns_start", interface_name, configuration))
        return handle

    def dns_server_stop(self, handle):
        self.operations.append(("dns_stop", handle)); self.dns[handle] = "stopped"

    def dns_server_status(self, handle):
        return self.dns[handle]


class NetworkServiceTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FakeNetworkServiceAdapter()
        base = RuntimeCapabilities.local(ROOT)
        self.host = replace(base, inspect_network=True, configure_network=True, host_network_services=True)

    def run_source(self, source, capabilities=None, adapter=None, environment=None):
        return execute(source, "network-service.sep", capabilities=capabilities or self.host,
                       network_adapter=adapter or self.adapter, environment_variables=environment)[1]

    def assert_error(self, source, code, capabilities=None, adapter=None, environment=None):
        with self.assertRaises(SeparanError) as caught:
            self.run_source(source, capabilities, adapter, environment)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_access_point_requires_secret_and_reports_redacted_status(self):
        source = '''function:main
wifi = wifi_open()
password = secret_from_environment("SETUP_PASSWORD")
wifi_start_access_point(wifi, ssid = "Separan-Device", password = password, channel = 6)
status = wifi_access_point_status(wifi)
print status.state
print status.ssid
print status.client_count
wifi_stop_access_point(wifi)
end_function:main
'''
        output = self.run_source(source, environment={"SETUP_PASSWORD": "setup-pass"})
        self.assertEqual(output, "running\nSeparan-Device\n2\n")
        configuration = self.adapter.operations[0][2]
        self.assertEqual(configuration["password"], b"setup-pass")
        self.assertNotIn("setup-pass", output)

    def test_access_point_rejects_open_or_short_password_and_bad_channel(self):
        def program(body): return f"function:main\nwifi = wifi_open()\n{body}\nend_function:main\n"
        self.assert_error(program('wifi_start_access_point(wifi, ssid = "Setup", password = "plaintext")'), "E201")
        self.assert_error(program('password = secret_from_environment("P")\nwifi_start_access_point(wifi, ssid = "Setup", password = password)'), "E984", environment={"P": "short"})
        self.assert_error(program('password = secret_from_environment("P")\nwifi_start_access_point(wifi, ssid = "Setup", password = password, channel = 0)'), "E984", environment={"P": "long-enough"})

    def test_access_point_rejects_duplicate_start_on_one_interface(self):
        source = '''function:main
wifi = wifi_open()
password = secret_from_environment("P")
wifi_start_access_point(wifi, ssid = "Setup", password = password)
wifi_start_access_point(wifi, ssid = "Setup-2", password = password)
end_function:main
'''
        self.assert_error(source, "E984", environment={"P": "long-enough"})

    def test_dhcp_server_configuration_status_leases_and_cleanup(self):
        source = '''object:empty
end_object:empty
function:main
wifi = wifi_open()
reserved = object_set(empty, "AA:BB:CC:DD:EE:90", "192.168.4.90")
dhcp = dhcp_server_start(wifi, server_address = "192.168.4.1", prefix = 24, pool_start = "192.168.4.10", pool_end = "192.168.4.50", gateway = "192.168.4.1", dns_servers = ["192.168.4.1"], lease_time = duration("1h"), reservations = reserved)
print dhcp_server_status(dhcp)
leases = dhcp_server_leases(dhcp)
print leases[0].address
print leases[0].hostname
end_function:main
'''
        output = self.run_source(source)
        self.assertEqual(output, "running\n192.168.4.10\nphone\n")
        configuration = next(item[2] for item in self.adapter.operations if item[0] == "dhcp_start")
        self.assertEqual(configuration["lease_time_ms"], 3_600_000)
        self.assertEqual(configuration["reservations"], {"AA:BB:CC:DD:EE:90": "192.168.4.90"})
        self.assertTrue(any(item[0] == "dhcp_stop" for item in self.adapter.operations))

    def test_dhcp_server_rejects_invalid_subnet_pool_limits_and_reservations(self):
        def source(extra="", pool_end="192.168.4.50", prefix=24):
            return f'''object:empty
end_object:empty
function:main
wifi = wifi_open()
reserved = empty
{extra}
dhcp_server_start(wifi, server_address = "192.168.4.1", prefix = {prefix}, pool_start = "192.168.4.10", pool_end = "{pool_end}", lease_time = duration("1h"), reservations = reserved)
end_function:main
'''
        self.assert_error(source(pool_end="192.168.5.10"), "E982")
        self.assert_error(source(pool_end="192.168.4.9"), "E982")
        limited = replace(self.host, max_dhcp_server_leases=4)
        self.assert_error(source(pool_end="192.168.4.20"), "E975", capabilities=limited)
        self.assert_error(source('reserved = object_set(reserved, "invalid", "192.168.4.90")'), "E982")
        self.assert_error(source('reserved = object_set(reserved, "AA:BB:CC:DD:EE:90", "192.168.4.20")'), "E982")

    def test_dns_server_normalizes_records_and_requires_explicit_catch_all(self):
        source = '''object:empty
end_object:empty
function:main
wifi = wifi_open()
records = object_set(empty, "Setup.Separan.", "192.168.4.1")
dns = dns_server_start(wifi, server_address = "192.168.4.1", records = records, catch_all = true)
print dns_server_status(dns)
dns_server_stop(dns)
print dns_server_status(dns)
end_function:main
'''
        self.assertEqual(self.run_source(source), "running\nstopped\n")
        configuration = next(item[2] for item in self.adapter.operations if item[0] == "dns_start")
        self.assertEqual(configuration, {"server_address": "192.168.4.1", "records": {"setup.separan": "192.168.4.1"}, "catch_all": True, "record_type": "A"})

    def test_dns_server_rejects_invalid_names_records_and_adapter_results(self):
        source = '''object:empty
end_object:empty
function:main
wifi = wifi_open()
records = object_set(empty, "bad_name", "192.168.4.1")
dns_server_start(wifi, server_address = "192.168.4.1", records = records)
end_function:main
'''
        self.assert_error(source, "E983")
        limited = replace(self.host, max_dns_server_records=0)
        source = source.replace('"bad_name"', '"setup.separan"')
        self.assert_error(source, "E975", capabilities=limited)
        empty = '''object:records
end_object:records
function:main
wifi = wifi_open()
dns_server_start(wifi, server_address = "192.168.4.1", records = records)
end_function:main
'''
        self.assert_error(empty, "E983")

    def test_service_hosting_is_a_separate_capability(self):
        inspect_only = replace(RuntimeCapabilities.local(ROOT), inspect_network=True, configure_network=True)
        caught = self.assert_error('function:main\nwifi = wifi_open()\npassword = secret_from_environment("P")\nwifi_start_access_point(wifi, ssid = "Setup", password = password)\nend_function:main\n', "E720", capabilities=inspect_only, environment={"P": "long-enough"})
        self.assertIn("host local network services", str(caught))

    def test_missing_adapter_operation_is_explicit(self):
        class InspectionOnly:
            def interfaces(inner): return self.adapter.interfaces()
        source = '''object:empty
end_object:empty
function:main
wifi = wifi_open()
records = object_set(empty, "setup.separan", "192.168.4.1")
dns_server_start(wifi, server_address = "192.168.4.1", records = records)
end_function:main
'''
        self.assert_error(source, "E978", adapter=InspectionOnly())

    def test_service_errors_are_catchable_as_network_error(self):
        source = '''function:main
try :host
wifi = wifi_open()
password = secret_from_environment("P")
wifi_start_access_point(wifi, ssid = "Setup", password = password, channel = 20)
catch network_error :host
print "caught"
endtry:host
end_function:main
'''
        self.assertEqual(self.run_source(source, environment={"P": "long-enough"}), "caught\n")


if __name__ == "__main__":
    unittest.main()
