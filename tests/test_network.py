import socket
import sys
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class FakeNetworkAdapter:
    def __init__(self):
        self.connected = True

    def interfaces(self):
        return [
            {
                "name": "ethernet0", "index": 1, "description": "Test Ethernet", "kind": "ethernet",
                "connected": False, "addresses": ["192.0.2.10"], "prefixes": [24],
                "gateways": ["192.0.2.1"], "dns_servers": ["1.1.1.1"],
                "mac_address": "00-11-22-33-44-55",
            },
            {
                "name": "wifi0", "index": 2, "description": "Test Wi-Fi", "kind": "wifi",
                "connected": self.connected, "addresses": ["2001:db8::10", "198.51.100.20"],
                "prefixes": [64, 24], "gateways": ["198.51.100.1"],
                "dns_servers": ["1.1.1.1", "2606:4700:4700::1111"],
                "mac_address": "AA-BB-CC-DD-EE-FF", "ssid": "Office-WiFi",
                "bssid": "11:22:33:44:55:66", "channel": 36, "signal_strength": 81,
            },
        ]

    def wifi_scan(self, interface_name):
        if interface_name != "wifi0":
            raise AssertionError(interface_name)
        return [
            {"ssid": "Weak", "signal_strength": 20, "channel": 1, "bssid": "00:00:00:00:00:01", "security": "wpa2_personal"},
            {"ssid": "Strong", "signal_strength": 90, "channel": 36, "bssid": "00:00:00:00:00:02", "security": "wpa3_personal"},
        ]


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.inspect = replace(RuntimeCapabilities.local(ROOT), inspect_network=True)
        self.adapter = FakeNetworkAdapter()

    def assert_error(self, source, code, capabilities=None, adapter=None):
        with self.assertRaises(SeparanError) as caught:
            execute(source, "network.sep", capabilities=capabilities, network_adapter=adapter)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_ip_address_is_a_strict_dedicated_type(self):
        source = '''ipv4 = ip_address("192.168.1.10")
ipv6 = ip_address("2001:db8::1")
print type(ipv4)
print ipv4
print ip_address_version(ipv4)
print ip_address_is_private(ipv4)
print ip_address_is_loopback(ip_address("127.0.0.1"))
print ip_address_is_global(ip_address("1.1.1.1"))
print ipv6
'''
        self.assertEqual(execute(source)[1], "ip_address\n192.168.1.10\n4\ntrue\ntrue\ntrue\n2001:db8::1\n")
        self.assert_error('print ip_address("999.1.1.1")\n', "E970")

    def test_interface_snapshot_and_common_accessors(self):
        source = '''interfaces = network_interfaces()
print length(interfaces)
wifi = network_interface("wifi0")
print type(wifi)
print wifi.name
print wifi.kind
print network_is_connected(wifi)
print network_ip_address(wifi)
print network_ip_addresses(wifi)
print network_gateway(wifi)
print network_subnet_mask(wifi)
print network_dns_servers(wifi)
print network_mac_address(wifi)
status = network_status(wifi)
print status.name
print type(status)
print network_hostname() == system.hostname
'''
        output = execute(source, capabilities=self.inspect, network_adapter=self.adapter)[1]
        self.assertEqual(output, "2\nnetwork_interface\nwifi0\nwifi\ntrue\n198.51.100.20\n[2001:db8::10, 198.51.100.20]\n198.51.100.1\n255.255.255.0\n[1.1.1.1, 2606:4700:4700::1111]\naa:bb:cc:dd:ee:ff\nwifi0\nobject\ntrue\n")

    def test_inspection_requires_explicit_capability(self):
        caught = self.assert_error("print network_interfaces()\n", "E720", RuntimeCapabilities.none(ROOT), self.adapter)
        self.assertIn("inspect network interfaces", str(caught))

    def test_interface_kind_selection_and_preference(self):
        source = '''function:main
wifi = wifi_open()
lan = ethernet_open("ethernet0")
print wifi.name
print lan.name
network_set_preferred_interfaces(["ethernet0", "wifi0"])
print network_preferred_interface().name
print ethernet_status(lan).connected
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.inspect, network_adapter=self.adapter)[1], "wifi0\nethernet0\nwifi0\nfalse\n")
        self.assert_error('print wifi_open("ethernet0")\n', "E972", self.inspect, self.adapter)
        self.assert_error('function:main\nnetwork_set_preferred_interfaces(["missing"])\nend_function:main\n', "E972", self.inspect, self.adapter)
        self.assert_error('function:main\nnetwork_set_preferred_interfaces(["wifi0", "wifi0"])\nend_function:main\n', "E972", self.inspect, self.adapter)

    def test_wifi_status_scan_and_wait(self):
        source = '''wifi = wifi_open()
print wifi_is_connected(wifi)
print wifi_ssid(wifi)
print wifi_bssid(wifi)
print wifi_channel(wifi)
print wifi_signal_strength(wifi)
networks = wifi_scan(wifi)
print networks[0].ssid
print networks[0].security
print wifi_wait_until_connected(wifi, duration("0s"))
'''
        self.assertEqual(execute(source, capabilities=self.inspect, network_adapter=self.adapter)[1], "true\nOffice-WiFi\n11:22:33:44:55:66\n36\n81\nStrong\nwpa3_personal\ntrue\n")
        self.adapter.connected = False
        self.assertEqual(execute('wifi = wifi_open()\nprint wifi_wait_until_connected(wifi, duration("0s"))\n', capabilities=self.inspect, network_adapter=self.adapter)[1], "false\n")

    def test_wifi_scan_unavailable_is_an_explicit_error(self):
        class Adapter(FakeNetworkAdapter):
            def wifi_scan(self, interface_name):
                raise NotImplementedError("scan backend unavailable")
        self.assert_error('wifi = wifi_open()\nprint wifi_scan(wifi)\n', "E978", self.inspect, Adapter())

    def test_dns_returns_all_addresses_deterministically(self):
        capability = replace(RuntimeCapabilities.local(ROOT), network=True,
                             network_hosts=frozenset({"example.test"}), allow_private_network=True)
        records = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::2", 0, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.2", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.2", 0)),
        ]
        with patch("separan.network.socket.getaddrinfo", return_value=records):
            output = execute('values = dns_resolve("example.test")\nprint values\nprint type(first(values))\n', capabilities=capability)[1]
        self.assertEqual(output, "[192.0.2.2, 2001:db8::2]\nip_address\n")

    def test_dns_reverse_absence_is_null(self):
        capability = replace(RuntimeCapabilities.local(ROOT), network=True,
                             network_hosts=frozenset({"192.0.2.2"}), allow_private_network=True)
        with patch("separan.network.socket.gethostbyaddr", side_effect=socket.herror()):
            self.assertEqual(execute('print dns_reverse_lookup(ip_address("192.0.2.2"))\n', capabilities=capability)[1], "null\n")

    def test_tcp_round_trip_uses_bytes_and_explicit_close(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0)); server.listen(1)
        port = server.getsockname()[1]
        received = []

        def serve():
            connection, _ = server.accept()
            with connection:
                received.append(connection.recv(32))
                connection.sendall(b"world")
            server.close()

        thread = threading.Thread(target=serve, daemon=True); thread.start()
        capability = replace(RuntimeCapabilities.local(ROOT), network=True,
                             network_hosts=frozenset({"127.0.0.1"}), network_ports=frozenset({port}),
                             allow_private_network=True)
        source = f'''function:main
connection = tcp_connect("127.0.0.1", {port}, timeout = duration("2s"))
print type(connection)
print tcp_send(connection, "hello")
reply = tcp_receive(connection, 32)
print type(reply)
print string_from_bytes(reply)
tcp_close(connection)
print connection
end_function:main
'''
        output = execute(source, capabilities=capability)[1]
        thread.join(2)
        self.assertEqual(received, [b"hello"])
        self.assertEqual(output, f"tcp_connection\n5\nbytes\nworld\ntcp_connection:127.0.0.1:{port} [CLOSED]\n")

    def test_udp_round_trip_and_response_metadata(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0)); port = server.getsockname()[1]

        def serve():
            data, sender = server.recvfrom(32)
            server.sendto(data.upper(), sender)
            server.close()

        thread = threading.Thread(target=serve, daemon=True); thread.start()
        capability = replace(RuntimeCapabilities.local(ROOT), network=True,
                             network_hosts=frozenset({"127.0.0.1"}), network_ports=frozenset({port}),
                             allow_private_network=True)
        source = f'''function:main
udp = udp_open(timeout = duration("2s"))
print type(udp)
print udp_send(udp, "127.0.0.1", {port}, "ping")
reply = udp_receive(udp, 32)
print string_from_bytes(reply.data)
print reply.address
print reply.port
udp_close(udp)
end_function:main
'''
        output = execute(source, capabilities=capability)[1]
        thread.join(2)
        self.assertEqual(output, f"udp_socket\n4\nPING\n127.0.0.1\n{port}\n")

    def test_udp_bind_requires_separate_capability(self):
        capability = replace(RuntimeCapabilities.local(ROOT), network=True)
        self.assert_error('print udp_open(local_address = "127.0.0.1", local_port = 0)\n', "E720", capability)
        allowed = replace(capability, bind_network=True,
                          network_bind_hosts=frozenset({"127.0.0.1"}), network_bind_ports=frozenset({0}))
        self.assertEqual(execute('udp = udp_open(local_address = "127.0.0.1", local_port = 0)\nprint type(udp)\n', capabilities=allowed)[1], "udp_socket\n")

    def test_host_port_private_and_receive_limits_are_enforced(self):
        denied_host = replace(RuntimeCapabilities.local(ROOT), network=True,
                              network_hosts=frozenset({"allowed.test"}), allow_private_network=True)
        self.assert_error('print dns_resolve("denied.test")\n', "E979", denied_host)

        denied_private = replace(RuntimeCapabilities.local(ROOT), network=True,
                                 network_hosts=frozenset({"localhost"}), allow_private_network=False)
        self.assert_error('print dns_resolve("localhost")\n', "E979", denied_private)

        limited = replace(RuntimeCapabilities.local(ROOT), network=True,
                          max_socket_receive_bytes=8)
        self.assert_error('udp = udp_open()\nprint udp_receive(udp, 9)\n', "E975", limited)

    def test_network_errors_are_catchable_by_parent_category(self):
        capability = replace(RuntimeCapabilities.local(ROOT), network=True,
                             network_hosts=frozenset({"missing.invalid"}))
        source = '''function:main
try :lookup
print dns_resolve("missing.invalid")
catch network_error :lookup
print "network failed"
endtry:lookup
end_function:main
'''
        self.assertEqual(execute(source, capabilities=capability)[1], "network failed\n")


if __name__ == "__main__":
    unittest.main()
