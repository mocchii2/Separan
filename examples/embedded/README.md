# Separan Embedded examples

These examples use logical pins and default buses from the selected board
profile. The same `.sep` source is validated for all six bundled Tier 1 boards:

- Raspberry Pi Pico, Pico W, Pico 2, and Pico 2 W
- Arduino Nano and Nano Every

```console
separan build 01_blink.sep --board raspberry_pi_pico
separan build 01_blink.sep --board raspberry_pi_pico_w
separan build 01_blink.sep --board arduino_nano
separan build 01_blink.sep --board arduino_nano_every
```

`01_blink.sep` is portable because it uses `pin.LED_BUILTIN`.
`01_blink_d13.sep` intentionally demonstrates a board-specific logical name.
Always use the portable form unless D13 itself is part of the hardware contract.

| File | Demonstrates |
|---|---|
| `01_blink.sep` | portable board LED output |
| `01_blink_d13.sep` | explicit D13 output |
| `02_button.sep` | pull-up digital input |
| `03_pwm_fade.sep` | normalized PWM output |
| `04_analog_read.sep` | A0 analog input |
| `05_uart_echo.sep` | default UART text I/O |
| `06_i2c_scan.sep` | default I²C bus probing |

The current build command performs parser-backed board mapping and capability
validation. It does not yet generate or upload firmware. SDK adapters for real
hardware are the next implementation layer.

Planned examples: `07_spi.sep`, `08_temperature_sensor.sep`,
`09_wifi_http.sep`, and `10_cloudwatch_sensor.sep`.

[日本語](README.ja.md)
