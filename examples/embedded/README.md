# Separan Embedded examples

These examples use logical pins and default buses from the selected board
profile. The same `.sep` source is validated for all six bundled Tier 1 boards:

- Raspberry Pi Pico, Pico W, Pico 2, and Pico 2 W
- Arduino Nano and Nano Every

```console
separan build 01_blink.sep --board raspberry_pi_pico
separan build 01_blink.sep --board raspberry_pi_pico_2
```

Those two commands generate C++, configure the official Pico SDK, compile, and
verify ELF, UF2, and HEX outputs. Pico W and Nano profiles remain available for
mapping validation:

```console
separan build 01_blink.sep --board raspberry_pi_pico_w --validate-only
separan build 01_blink.sep --board arduino_nano --validate-only
```

Use `--emit-only` when you want to inspect the generated project without an
installed SDK. If the official Raspberry Pi Pico extension is not installed,
pass the tool locations explicitly:

```console
separan build 01_blink.sep --board raspberry_pi_pico_2 \
  --sdk-path /path/to/pico-sdk --cmake cmake --ninja ninja
```

To deploy, hold BOOTSEL while connecting the board and name that mounted device
root explicitly. Separan refuses unmarked directories:

```console
separan flash build/01_blink-raspberry_pi_pico/build/separan_app_01_blink.uf2 --device E:\
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

The firmware preview currently targets non-wireless Raspberry Pi Pico and Pico
2. GPIO, ADC, PWM, I²C probing, text UART, delays, strict expressions, functions,
and core control flow are generated. Pico W CYW43 control, SPI firmware calls,
networking, and Arduino Core generation remain explicit follow-ups.

Planned examples: `07_spi.sep`, `08_temperature_sensor.sep`,
`09_wifi_http.sep`, and `10_cloudwatch_sensor.sep`.

[日本語](README.ja.md)
