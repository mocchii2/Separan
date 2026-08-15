# Separan Embeddedサンプル

各サンプルは、選択したboard profileの論理pinとdefault busを使います。同じ`.sep`
sourceを、同梱するTier 1 board 6機種すべてに対して検証できます。

- Raspberry Pi Pico、Pico W、Pico 2、Pico 2 W
- Arduino Nano、Nano Every

```console
separan build 01_blink.sep --board raspberry_pi_pico
separan build 01_blink.sep --board raspberry_pi_pico_2
```

この2コマンドはC++生成、公式Pico SDK configure／compile、ELF／UF2／HEX確認まで
実行します。Pico WとNano profileはmapping検証に引き続き利用できます。

```console
separan build 01_blink.sep --board raspberry_pi_pico_w --validate-only
separan build 01_blink.sep --board arduino_nano --validate-only
```

SDKなしで生成projectだけ確認する場合は`--emit-only`を使います。公式Raspberry Pi Pico
拡張を導入していない環境ではtool pathを明示できます。

```console
separan build 01_blink.sep --board raspberry_pi_pico_2 \
  --sdk-path /path/to/pico-sdk --cmake cmake --ninja ninja
```

書き込み時はBOOTSELを押して接続し、mountされたdevice rootを明示します。UF2 markerが
ないdirectoryへのcopyは拒否します。

```console
separan flash build/01_blink-raspberry_pi_pico/build/separan_app_01_blink.uf2 --device E:\
```

`01_blink.sep`は`pin.LED_BUILTIN`を使うportable版です。
`01_blink_d13.sep`は意図的にboard-specificなlogical nameを使う例です。hardware contract
自体がD13を要求する場合以外はportable版を使います。

| File | 内容 |
|---|---|
| `01_blink.sep` | portable board LED output |
| `01_blink_d13.sep` | 明示的なD13 output |
| `02_button.sep` | pull-up digital input |
| `03_pwm_fade.sep` | 正規化PWM output |
| `04_analog_read.sep` | A0 analog input |
| `05_uart_echo.sep` | default UART text I/O |
| `06_i2c_scan.sep` | default I²C bus probe |

firmware previewの対象はnon-wireless Raspberry Pi Pico／Pico 2です。GPIO、ADC、PWM、
I²C probe、text UART、delay、strict expression、function、基本control flowを生成します。
Pico WのCYW43制御、SPI firmware call、networking、Arduino Core生成は今後の明示的な
実装対象です。

今後は`07_spi.sep`、`08_temperature_sensor.sep`、`09_wifi_http.sep`、
`10_cloudwatch_sensor.sep`を予定しています。

[English](README.md)
