# Separan Embedded Board Mapping仕様 — preview v0.1

状態: **Pythonリファレンス処理系へ実験実装済み**。論理board profile、capability検証、
`build --board`の静的検証、host adapter境界を実装しています。Raspberry Pi Picoと
Pico 2ではPico SDK向けC++生成、SDK compile、UF2／HEX生成、明示BOOTSEL書き込みまで
実装済みです。wireless PicoとArduinoのfirmware backendは未実装です。

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
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico
```

`build`はprogram全体をparseし、実行されないfunction内も含む直接の`pin.NAME`参照を
静的検証します。Pico／Pico 2では続けてC++とPico SDK CMake projectを生成し、shellを
介さずCMake／Ninjaを実行してELF、UF2、HEXが揃ったことまで検証します。

```console
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico_2
```

公式Raspberry Pi Pico VS Code拡張を導入するか、`--sdk-path`、`--toolchain-path`、
`--cmake`、`--ninja`を明示します。default生成先は`build/<source>-<board>`です。
`--emit-only`はsource生成で停止し、`--validate-only`は全Tier 1 boardで従来のprofile検証だけを
行います。

UF2書き込み先は自動推測しません。boardをBOOTSEL modeにしてmount rootを明示し、
`INFO_UF2.TXT`にUF2 bootloader metadataが存在する場合だけcopyします。

```console
separan flash build/01_blink-raspberry_pi_pico/build/separan_app_01_blink.uf2 --device E:\
```

## 実装済みTier 1 profile

| Profile ID | MCU | Logic | Wireless | Firmware backend |
|---|---|---:|---|---|
| `raspberry_pi_pico` | RP2040 | 3.3 V | なし | Pico SDK (`pico`) |
| `raspberry_pi_pico_w` | RP2040 | 3.3 V | Wi-Fi、Bluetooth | validation only |
| `raspberry_pi_pico_2` | RP2350 | 3.3 V | なし | Pico SDK (`pico2`) |
| `raspberry_pi_pico_2_w` | RP2350 | 3.3 V | Wi-Fi、Bluetooth | validation only |
| `arduino_nano` | ATmega328P | 5 V | なし | validation only |
| `arduino_nano_every` | ATmega4809 | 5 V | なし | validation only |

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
- `delay_milliseconds(value)`、`i2c_probe(bus, address)`
- `uart_write(bus, value)`、`uart_read_line(bus)`

`analog_write`はcapability検証付きcontractとして存在しますが、現在のTier 1 profileに
true DAC outputはありません。PWMは`pwm_write`へ明示します。analog／PWM output値は
0以上1以下です。

bus indexとsignal roleは同じperipheral instanceに属する必要があります。I²C1 SDA対応pinを
I²C0 SDAとして黙って受け付けません。pin省略時はprofileのdeterministic default mappingを
使います。

desktop interpreter上のhardware操作にはhostの`embedded_io` capabilityが必要で、
`embedded_boards` allowlistでも制限できます。Python interpreterのvalidation adapterは
副作用なしのままです。別のPico firmware generatorはreview済みoperationをtyped Pico SDK
callへ変換し、shell command fallbackやraw source置換を行いません。

初期generatorはfunction、assignment／const、strict expression、`if`／`while`、
`number_range`とliteral listの`for`、print、GPIO、ADC、PWM、I2C probe、text UART、delayを
扱います。未対応のdynamic／desktop専用構文は部分的C++を黙って出さず`E966`で停止します。
SPI firmware call、Pico WのCYW43 LED、networking、heap-shaped object、Arduino Core生成は
まだ対応を主張しません。

`delay_milliseconds`はdesktop上の隠れたsleepではなくadapter operationです。integer入力は
1日までに制限します。`i2c_probe`は0から127までの明示的な7-bit addressを受け取り
booleanを返します。text UART操作はstringを使い、将来のbinary UART操作では暗黙encodingを
行わずbytesを使います。

## 公式portableサンプル

同じ[`01_blink.sep`](../examples/embedded/01_blink.sep) sourceを現在のPico／Nano Tier 1
targetすべてに対して検証でき、Pico／Pico 2ではfirmwareまで生成できます。
portable形式は`pin.LED_BUILTIN`です。
[`01_blink_d13.sep`](../examples/embedded/01_blink_d13.sep)は意図的にboard-specificな
`pin.D13`を選ぶ例です。

| Example | 検証するcontract |
|---|---|
| `01_blink.sep` | logical board LED、GPIO output、bounded delay |
| `02_button.sep` | pull-up付きdigital inputとboard LED output |
| `03_pwm_fade.sep` | profile共通pin上の正規化PWM duty cycle |
| `04_analog_read.sep` | `pin.A0` analog capabilityと`number_range` |
| `05_uart_echo.sep` | default UART mappingと明示的string I/O |
| `06_i2c_scan.sep` | default I²C mappingと7-bit address probe |

今後は`07_spi.sep`、`08_temperature_sensor.sep`、`09_wifi_http.sep`、
`10_cloudwatch_sensor.sep`を予定します。対応するtyped adapter contractが存在する機能だけを
sampleへ追加し、mapping検証だけでhardware実行できるような記述はしません。

## 診断

| Code | 意味 |
|---|---|
| `E960` | board未選択、未知、またはlock済みbuild targetとの不一致 |
| `E961` | 未知pin、または別profile由来のpin |
| `E962` | requested pin capabilityがない |
| `E963` | bus signalとperipheral instanceの組み合わせが不正 |
| `E964` | adapter未接続、失敗、または戻り型不正 |
| `E965` | GPIO mode、delay、address、またはanalog／PWM値が不正 |
| `E966` | firmware backendまたはsource構文が未対応 |
| `E967` | Pico SDK、CMake、Ninja、toolchainが利用不可 |
| `E968` | SDK configure／compile失敗、または成果物不足 |
| `E969` | UF2 image、BOOTSEL target、device writeが不正 |

## Hardware data source

community pin表ではなくvendor公式情報からprofileを作成します。

- [Raspberry Pi Pico series公式document／pinout](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [Raspberry Pi Pico SDK hardware API](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html)
- [Arduino Nano公式document](https://docs.arduino.cc/hardware/nano/)
- [Arduino Nano Every公式document](https://docs.arduino.cc/hardware/nano-every/)

pinの意味を変えるprofile変更は互換性に影響するため、conformance testを必須とします。
