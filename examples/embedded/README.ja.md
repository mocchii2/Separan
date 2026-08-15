# Separan Embeddedサンプル

各サンプルは、選択したboard profileの論理pinとdefault busを使います。同じ`.sep`
sourceを、同梱するTier 1 board 6機種すべてに対して検証できます。

- Raspberry Pi Pico、Pico W、Pico 2、Pico 2 W
- Arduino Nano、Nano Every

```console
separan build 01_blink.sep --board raspberry_pi_pico
separan build 01_blink.sep --board raspberry_pi_pico_w
separan build 01_blink.sep --board arduino_nano
separan build 01_blink.sep --board arduino_nano_every
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

現在のbuild commandはParser連動のboard mapping／capability検証を行います。firmwareの
生成とuploadはまだ行いません。実機用SDK adapterが次の実装層です。

今後は`07_spi.sep`、`08_temperature_sensor.sep`、`09_wifi_http.sep`、
`10_cloudwatch_sensor.sep`を予定しています。

[English](README.md)
