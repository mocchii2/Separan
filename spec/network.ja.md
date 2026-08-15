# Separan Native Network仕様 v0.1

状態: Separan `0.2.0-alpha.8`で実験実装済み。

## 目的と境界

native network APIはPC／server上のscript向けです。HTTP、および
Embedded／Micro Separanのdriver層とは分離します。この仕様にはboard固有Wi-Fi driver、
GPIO接続Ethernet controller、firmware生成、AP hosting、hardware safety検証を含めません。

権限は次の3つへ分離します。

- `inspect_network`: hostのinterface状態を読む
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

Wi-Fi接続／切断、DHCP／固定address変更、machine hostname変更、AP開始はnative previewに
入れません。machine全体を書き換え、管理者権限やplatform固有credential modelを必要と
するためです。

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

capability拒否は`network_error`ではなく`permission_error`です。host policy違反と
通信失敗を区別できます。

Windows native実装は管理者権限やPowerShellへ依存せずIP Helper APIを利用します。
Linuxは`ip`のJSON dataと`/etc/resolv.conf`を利用し、その他platformでは保守的な
standard-library fallbackを使用します。
