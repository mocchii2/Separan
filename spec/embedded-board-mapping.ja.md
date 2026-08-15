# Separan Embedded Board Mapping仕様 — preview v0.1

状態: **Pythonリファレンス処理系へ実験実装済み**。論理board profile、capability検証、
`build --board`の静的検証、host adapter境界まで実装しています。firmware生成と
Arduino Core／Pico SDK adapterはまだ同梱していません。

## 原則

application codeは意図を名前で表し、物理pinとperipheralの対応はversion管理された
Separan board profileが所有します。

```text
Separan source -> logical pin -> board profile -> host adapter -> board SDK
```

利用者にboard固有の数値pin表を転記させません。profileはphysical header位置、backend
識別子、logic voltage、capability、有効なperipheral instanceを保持します。既知の不正な
組み合わせはadapterがhardwareへ触れる前に拒否します。

```separan
board = board_select("raspberry_pi_pico")

function:main
gpio_set_mode(pin.LED_BUILTIN, "output")
gpio_write(pin.LED_BUILTIN, true)
sensor_bus = i2c_open(0)
end_function:main
```

build targetをsource外から指定することもできます。

```console
separan build examples/embedded_blink.sep --board raspberry_pi_pico
```

現在の`build`はprogram全体をparseし、実行されないfunction内も含む直接の`pin.NAME`
参照を静的検証します。「mapping validation only」であることを明示し、firmwareを生成した
とは表示しません。

## 実装済みTier 1 profile

| Profile ID | Family | MCU | Logic | Wireless |
|---|---|---|---:|---|
| `raspberry_pi_pico` | Raspberry Pi Pico | RP2040 | 3.3 V | なし |
| `raspberry_pi_pico_w` | Raspberry Pi Pico | RP2040 | 3.3 V | Wi-Fi、Bluetooth |
| `raspberry_pi_pico_2` | Raspberry Pi Pico | RP2350 | 3.3 V | なし |
| `raspberry_pi_pico_2_w` | Raspberry Pi Pico | RP2350 | 3.3 V | Wi-Fi、Bluetooth |
| `arduino_nano` | Arduino Nano | ATmega328P | 5 V | なし |
| `arduino_nano_every` | Arduino Nano | ATmega4809 | 5 V | なし |

Pico profileが公開するraw GPIOはheaderへ出ている`GP0`から`GP22`、`GP26`から`GP28`
だけです。portable aliasとして`D0`、`A0`、`SDA`、`SCL`、`TX`、`RX`、`MOSI`、
`MISO`、`SCK`、`LED_BUILTIN`も提供します。Pico Wのonboard LEDをRP GPIO25に
偽装せず、wireless controller用backend identityへ解決します。

Classic Nanoの`A6`／`A7`はanalog-onlyです。Nano Everyはconnector互換でもMCUと
capabilityが異なるため、別profileとして扱います。

`arduino_nano_33_iot`、`arduino_nano_33_ble`、`arduino_nano_33_ble_sense`、
`arduino_nano_rp2040_connect`、`arduino_nano_esp32`は計画中です。公式pin／peripheral
dataのreviewが終わるまでaccepted aliasにしません。似たboardへの暗黙置換は禁止です。

## 読み取り専用board／pin API

`pin`は`system`と同じ予約済みreadonly namespaceで、shadowできません。

| API | 結果 |
|---|---|
| `board_select(id)` | profileを選択し`board`値を返す |
| `board_name()`／`board_family()`／`board_cpu()` | 正規化済みprofile metadata |
| `board_voltage()` | logic voltageのnumber |
| `board_has(feature)` | feature完全一致判定 |
| `board_pins()`／`board_features()` | deterministicなpin／feature list |
| `pin_exists(name)` | 現profileのpinまたはaliasか |
| `pin_has(pin, capability)` | capability完全一致判定 |
| `pin_capabilities(pin)` | capability名list |

board memberは`id`、`name`、`family`、`cpu`、`voltage`、`flash_bytes`、
`ram_bytes`、`features`。pin memberは`name`、`physical_pin`、`backend_pin`、
`voltage`、`capabilities`です。

## Hardware APIと検証

adapter向けに次を実装しています。

- `gpio_set_mode(pin, mode)`、`gpio_write(pin, boolean)`、`gpio_read(pin)`
- `analog_read(pin)`、`analog_write(pin, value)`、`pwm_write(pin, duty_cycle)`
- `i2c_open([index], sda=..., scl=...)`
- `spi_open([index], mosi=..., miso=..., clock=..., chip_select=...)`
- `uart_open([index], tx=..., rx=...)`

`analog_write`はcapability検証付きcontractとして存在しますが、現在のTier 1 profileに
true DAC outputはありません。PWMは`pwm_write`へ明示します。analog／PWM output値は
0以上1以下です。

bus indexとsignal roleは同じperipheral instanceに属する必要があります。I²C1 SDA対応pinを
I²C0 SDAとして黙って受け付けません。pin省略時はprofileのdeterministic default mappingを
使います。

hardware操作にはhostの`embedded_io` capabilityが必要で、`embedded_boards` allowlistでも
制限できます。その後、明示的に注入されたadapterだけを呼びます。Python referenceには
副作用のないvalidation adapterだけを同梱し、raw register accessやshell command fallbackは
行いません。

## 診断

| Code | 意味 |
|---|---|
| `E960` | board未選択、未知、またはlock済みbuild targetとの不一致 |
| `E961` | 未知pin、または別profile由来のpin |
| `E962` | requested pin capabilityがない |
| `E963` | bus signalとperipheral instanceの組み合わせが不正 |
| `E964` | adapter未接続、失敗、または戻り型不正 |
| `E965` | GPIO modeまたはanalog／PWM値が不正 |

## Hardware data source

community pin表ではなくvendor公式情報からprofileを作成します。

- [Raspberry Pi Pico series公式document／pinout](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [Raspberry Pi Pico SDK hardware API](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html)
- [Arduino Nano公式document](https://docs.arduino.cc/hardware/nano/)
- [Arduino Nano Every公式document](https://docs.arduino.cc/hardware/nano-every/)

pinの意味を変えるprofile変更は互換性に影響するため、conformance testを必須とします。
