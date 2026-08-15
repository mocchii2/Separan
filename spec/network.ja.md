# Separan Native Network仕様 v0.1

状態: Separan `0.2.0-alpha.11`で実験実装済み。

## 目的と境界

native network APIはPC／server上のscript向けです。HTTP、および
Embedded／Micro Separanのdriver層とは分離します。この仕様にはboard固有Wi-Fi driver、
GPIO接続Ethernet controller、firmware生成、AP hosting、hardware safety検証を含めません。

権限は次の4つへ分離します。

- `inspect_network`: hostのinterface状態を読む
- `configure_network`: 明示adapterを通じてIP設定変更を要求する
- `network`: 明示許可された宛先host／portを名前解決・通信する
- `bind_network`: 明示許可されたlocal address／portへUDP socketをbindする

source programが自分で権限を増やすことはできません。hostはtimeoutと受信byte数にも
上限を設定できます。private、loopback、link-local等の非global宛先は、
`allow_private_network`が有効でなければ拒否します。

## 専用値型

`ip_address(text)`は不変のIPv4／IPv6値を生成します。不正文字列をstringのまま
保持せず、`E970`で停止します。

```separan
address = ip_address("192.168.1.10")

print ip_address_version(address)
print ip_address_is_private(address)
print ip_address_is_loopback(address)
print ip_address_is_global(address)
```

ほかの公開型は`network_interface`、`tcp_connection`、`udp_socket`です。
TCP／UDP resourceは`tcp_close`／`udp_close`で閉じ、program終了時にはruntimeが
未close resourceも自動closeします。

## Interface照会

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

`network_ip_address`は非loopback IPv4を優先し、なければ最初のaddressを返します。
複数IPv4／IPv6を隠さないため、完全なsnapshotは`network_ip_addresses`で取得します。
単一値の不在はnull、collectionの不在は空listです。

`network_status(interface)`は`name`、`kind`、`connected`、`ip_address`、
`gateway`、`subnet_mask`、`dns_servers`、`mac_address`を持つ不変objectです。
kindは`ethernet`、`wifi`、`loopback`、`other`のいずれかです。

優先順はruntime内だけの状態で、OS routingを書き換えません。

```separan
network_set_preferred_interfaces(["Ethernet", "Wi-Fi"])
active = network_preferred_interface()
```

指定順で最初のconnected interfaceを返し、なければnullです。

## Ethernet／Wi-Fi view

`ethernet_open([name])`と`wifi_open([name])`は既存host interfaceを選択します。
hardwareをopenしたりOS設定を変更したりする関数ではありません。

```separan
wifi = wifi_open()

print wifi_is_connected(wifi)
print wifi_ssid(wifi)
print wifi_bssid(wifi)
print wifi_channel(wifi)
print wifi_signal_strength(wifi)

networks = wifi_scan(wifi)
```

scan recordは`ssid`、`signal_strength`、`channel`、`bssid`、`security`を持ち、
signal降順、SSID順で決定的に並びます。native previewのscanはLinuxの
NetworkManager `nmcli`を利用します。安全なnative scannerがないplatformでは、
偽の空listではなく`network_operation_unavailable`を返します。

`wifi_wait_until_connected(wifi, timeout)`は同じinterface identityの最新host状態を
確認してbooleanを返します。duration 0なら1回だけ確認します。

Wi-Fi接続／切断、machine hostname変更、AP開始はnative previewに入れません。それぞれ
credentialとmachine全体のpolicyが別途必要だからです。

## 共通IP address設定

address設定はlink typeから独立しています。同じAPIへEthernetまたはWi-Fiの
`network_interface`を渡します。

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

公開する設定操作は次です。

- `network_use_dhcp(interface)`
- `network_set_static_address(interface, address, prefix, gateway, dns)`
- `network_use_link_local(interface)`
- `network_refresh_address(interface)`／`network_release_address(interface)`
- `network_enable_link_local_fallback(interface)`／
  `network_disable_link_local_fallback(interface)`

固定addressとgatewayは同じIP versionでなければならず、prefix範囲もversionに合わせて
検証します。gatewayはnull、DNSは重複のない明示listにできます。固定link-local addressは
拒否し、意図が名前に出る`network_use_link_local`を使用します。

`network_address_mode(interface)`は`disabled`、`dhcp`、`static`、`link_local`、`unknown`
のいずれかです。`unknown`はread-only host inspectorが設定方式を証明できない状態であり、
Separanが推測で補うことはありません。

`network_dhcp_status(interface)`は`disabled`、`discovering`、`requesting`、`bound`、
`renewing`、`rebinding`、`failed`のいずれかです。
`network_dhcp_lease(interface)`はlease不在ならnull、存在すれば次の不変objectを返します。

- `address`、`prefix`、`gateway`、`dns_servers`
- `server_address`
- null許容durationの`lease_duration`、`renew_after`、`rebind_after`
- null許容UTC datetimeの`expires_at`

adapter由来dataも型、範囲、時間順序を検証します。不正leaseを部分的に信用せず、
`E980 network_address_error`で停止します。

link-local fallbackはdefault無効です。DHCP失敗時にprogramが明示許可しない限り、
Separanが169.254/16へ切り替えることはありません。明示link-local modeとfallbackの
duplicate-address検査はadapter側network stackへ委譲します。

設定には独立した`configure_network` capabilityが必要です。CLIでは
`--allow-network-configuration`を指定します。このflagは対象選択に必要なinterface照会も
許可しますが、外向きnetwork権限は付与しません。desktopのdefault
`NativeNetworkAdapter`はread-onlyのままで、設定要求には
`network_operation_unavailable`を返します。host／embedded runtimeが実装するcontractは
次です。

```text
use_dhcp(interface_name)
set_static_address(interface_name, configuration)
use_link_local(interface_name)
refresh_address(interface_name)
release_address(interface_name)
set_link_local_fallback(interface_name, enabled)
```

adapterはNetworkManager／OS native設定、lwIP、Pico SDK、ESP-IDF、Arduino network stackを
呼びます。Separanは意図、状態名、型付き結果、timeout、capability、診断を担当し、DHCP
clientを二重実装しません。このmodelは[RFC 2131](https://www.rfc-editor.org/rfc/rfc2131)の
DHCP client状態／lease modelに沿い、IPv4 link-localは
[RFC 3927](https://www.rfc-editor.org/rfc/rfc3927)どおり明示機能にします。
完全なsourceひな形は
[`examples/network_addressing.sep`](../examples/network_addressing.sep)にあります。

## DNS

```separan
addresses = dns_resolve("api.example.com")
name = dns_reverse_lookup(ip_address("203.0.113.10"))
```

`dns_resolve`は任意の1件を選ばず、重複除去・決定的sort済みの
`list<ip_address>`を返します。名前解決失敗は`network_dns_error`、逆引き不在は
正常なnullです。どちらもhost allowlistとprivate-address規則を適用します。

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

`tcp_send`はstringまたはbytesを受け、stringはUTF-8で送信してbyte数を返します。
`tcp_receive`は正常EOFの空値を含め、必ずbytesを返します。text化は
`string_from_bytes`で明示します。接続前に解決済みaddressを検証し、検証した数値addressへ
直接接続します。

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

`packet.data`はbytes、`packet.address`はip_address、`packet.port`はnumberです。
受信待ちを先に行う場合は明示bindできます。

```separan
socket = udp_open(
    local_address = "127.0.0.1",
    local_port = 9000
)
```

bindには別の`bind_network` capabilityとlocal address／port allowlistが必要です。
`local_address`／`local_port`の片方だけを指定するとerrorです。

## Errorとlimit

次の詳細errorはすべて`network_error`でcatchできます。

- `network_dns_error`
- `network_interface_error`
- `network_connection_error`
- `network_timeout_error`
- `network_limit_error`
- `network_closed_error`
- `network_protocol_error`
- `network_operation_unavailable`
- `network_address_error`

capability拒否は`network_error`ではなく`permission_error`です。host policy違反と
通信失敗を区別できます。

Windows native実装は管理者権限やPowerShellへ依存せずIP Helper APIを利用します。
Linuxは`ip`のJSON dataと`/etc/resolv.conf`を利用し、その他platformでは保守的な
standard-library fallbackを使用します。
