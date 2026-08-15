# Separan Embedded Board Mapping Specification — preview v0.1

Status: **experimental reference implementation**. Logical board profiles,
capability validation, static `build --board` validation, and the host-adapter
boundary are implemented. Raspberry Pi Pico and Pico 2 additionally have a
Pico SDK C++ generator, SDK compiler driver, UF2/HEX output, and explicit
BOOTSEL flashing. Wireless Pico and Arduino firmware backends remain pending.

## Principle

Application code names intent. A versioned Separan board profile owns the
physical and peripheral mapping:

```text
Separan source -> logical pin -> board profile -> host adapter -> board SDK
```

Users must not copy board-specific numeric pin tables into otherwise portable
source. A pin profile describes its physical header position, backend identity,
logic voltage, capabilities, and valid peripheral instances. Separan rejects a
known-invalid mapping before an adapter can touch hardware.

```separan
board = board_select("raspberry_pi_pico")

function:main
gpio_set_mode(pin.LED_BUILTIN, "output")
gpio_write(pin.LED_BUILTIN, true)
sensor_bus = i2c_open(0)
end_function:main
```

The build target can instead be supplied outside source:

```console
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico
```

The `build` command parses the complete program and validates every direct
`pin.NAME` reference, including references in functions that are not executed.
For Pico and Pico 2 it then emits C++ and a Pico SDK CMake project, invokes
CMake/Ninja without a shell, and requires ELF, UF2, and HEX artifacts:

```console
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico
separan build examples/embedded/01_blink.sep --board raspberry_pi_pico_2
```

Install the official Raspberry Pi Pico VS Code extension, or pass
`--sdk-path`, `--toolchain-path`, `--cmake`, and `--ninja` explicitly. The
default project directory is `build/<source>-<board>`. `--emit-only` stops
after deterministic source generation and `--validate-only` preserves the
profile-validation workflow for every Tier 1 board.

UF2 deployment never guesses a drive. Put the board into BOOTSEL mode and name
the mounted root explicitly; Separan requires valid UF2 bootloader metadata in
its `INFO_UF2.TXT` before copying:

```console
separan flash build/01_blink-raspberry_pi_pico/build/separan_app_01_blink.uf2 --device E:\
```

## Implemented Tier 1 profiles

| Profile ID | MCU | Logic | Wireless | Firmware backend |
|---|---|---:|---|---|
| `raspberry_pi_pico` | RP2040 | 3.3 V | no | Pico SDK (`pico`) |
| `raspberry_pi_pico_w` | RP2040 | 3.3 V | Wi-Fi, Bluetooth | validation only |
| `raspberry_pi_pico_2` | RP2350 | 3.3 V | no | Pico SDK (`pico2`) |
| `raspberry_pi_pico_2_w` | RP2350 | 3.3 V | Wi-Fi, Bluetooth | validation only |
| `arduino_nano` | ATmega328P | 5 V | no | validation only |
| `arduino_nano_every` | ATmega4809 | 5 V | no | validation only |

Pico profiles expose only GPIOs available on the board headers: `GP0` through
`GP22`, plus `GP26` through `GP28`. They also provide portable aliases such as
`D0`, `A0`, `SDA`, `SCL`, `TX`, `RX`, `MOSI`, `MISO`, `SCK`, and
`LED_BUILTIN`. Pico W boards do not pretend that the onboard LED is RP GPIO25;
their LED alias uses the wireless-controller backend identity.

Classic Nano `A6` and `A7` remain analog-only. Nano Every is a separate profile
despite its connector compatibility because its MCU and capabilities are not
the Classic Nano's.

Planned profiles are `arduino_nano_33_iot`, `arduino_nano_33_ble`,
`arduino_nano_33_ble_sense`, `arduino_nano_rp2040_connect`, and
`arduino_nano_esp32`. They are not accepted aliases until their official pin
and peripheral data has been reviewed; silently substituting a similar board
would violate this specification.

## Read-only board and pin APIs

`pin` is a reserved read-only namespace, like `system`. It cannot be shadowed.

| API | Result |
|---|---|
| `board_select(id)` | select and return a `board` value |
| `board_name()` / `board_family()` / `board_cpu()` | normalized profile metadata |
| `board_voltage()` | logic voltage as `number` |
| `board_has(feature)` | exact feature test |
| `board_pins()` / `board_features()` | deterministic sorted pins / profile features |
| `pin_exists(name)` | whether the current profile defines the name or alias |
| `pin_has(pin, capability)` | exact capability test |
| `pin_capabilities(pin)` | capability names |

Board members are `id`, `name`, `family`, `cpu`, `voltage`, `flash_bytes`,
`ram_bytes`, and `features`. Pin members are `name`, `physical_pin`,
`backend_pin`, `voltage`, and `capabilities`.

## Hardware APIs and validation

Implemented adapter-facing functions are:

- `gpio_set_mode(pin, mode)`, `gpio_write(pin, boolean)`, `gpio_read(pin)`
- `analog_read(pin)`, `analog_write(pin, value)`, `pwm_write(pin, duty_cycle)`
- `i2c_open([index], sda=..., scl=...)`
- `spi_open([index], mosi=..., miso=..., clock=..., chip_select=...)`
- `uart_open([index], tx=..., rx=...)`
- `delay_milliseconds(value)`, `i2c_probe(bus, address)`
- `uart_write(bus, value)`, `uart_read_line(bus)`

`analog_write` exists as a capability-checked contract; none of the current
Tier 1 profiles advertises a true DAC output. `pwm_write` is the explicit PWM
operation. Analog and PWM output values use the closed range 0 through 1.

Bus index and signal role must match the selected peripheral instance. A pin
that can act as I²C1 SDA is not silently accepted as I²C0 SDA. Omitting pin
arguments uses the profile's deterministic default bus mapping.

Hardware operations executed by the desktop interpreter require the host's
`embedded_io` capability and may be restricted to an `embedded_boards`
allowlist. The Python interpreter keeps its side-effect-free validation adapter.
The separate Pico firmware generator lowers reviewed operations directly to
typed Pico SDK calls; it never falls back to a shell command or raw source
substitution.

The first generator covers functions, assignments and constants, strict
expressions, `if`/`while`, `number_range` and literal-list `for` loops, print,
GPIO, ADC, PWM, I2C probing, text UART, and bounded delays. Unsupported dynamic
or desktop-only constructs fail with `E966` instead of producing partial C++.
SPI firmware calls, Pico W CYW43 LED control, networking, heap-shaped Separan
objects, and Arduino Core generation are deliberately not claimed yet.

`delay_milliseconds` is an adapter operation, not a hidden desktop sleep. Its
integer input is bounded to one day. `i2c_probe` accepts an explicit 7-bit
address from 0 through 127 and returns boolean. Text UART operations use string;
future binary UART operations will use bytes rather than implicit encoding.

## Official portable examples

The same [`01_blink.sep`](../examples/embedded/01_blink.sep) source validates
for every current Pico and Nano Tier 1 target and generates firmware for Pico
and Pico 2. `pin.LED_BUILTIN` is the portable form.
[`01_blink_d13.sep`](../examples/embedded/01_blink_d13.sep) demonstrates an
intentionally board-specific `pin.D13` choice.

| Example | Contract exercised |
|---|---|
| `01_blink.sep` | logical board LED, GPIO output, bounded delay |
| `02_button.sep` | digital input with pull-up and board LED output |
| `03_pwm_fade.sep` | normalized PWM duty cycle on a cross-profile pin |
| `04_analog_read.sep` | `pin.A0` analog capability and `number_range` |
| `05_uart_echo.sep` | default UART mapping and explicit string I/O |
| `06_i2c_scan.sep` | default I²C mapping and 7-bit address probing |

Planned follow-ups are `07_spi.sep`, `08_temperature_sensor.sep`,
`09_wifi_http.sep`, and `10_cloudwatch_sensor.sep`. A sample is added only when
the corresponding typed adapter contract exists; documentation must not imply
hardware execution from mapping validation alone.

## Diagnostics

| Code | Meaning |
|---|---|
| `E960` | board missing, unknown, or different from locked build target |
| `E961` | unknown pin or pin from a different profile |
| `E962` | requested pin capability is unavailable |
| `E963` | bus signal and peripheral instance do not form a valid mapping |
| `E964` | adapter missing, failed, or returned the wrong type |
| `E965` | invalid GPIO mode, delay, address, or analog/PWM value |
| `E966` | unsupported board backend or source construct for firmware generation |
| `E967` | Pico SDK, CMake, Ninja, or toolchain is unavailable |
| `E968` | SDK configuration/compilation failed or required artifacts are missing |
| `E969` | invalid UF2 image, BOOTSEL target, or device write |

## Hardware data sources

Profiles are derived from vendor documentation, not community pin tables:

- [Raspberry Pi Pico-series documentation and pinout files](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [Raspberry Pi Pico SDK hardware APIs](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html)
- [Arduino Nano documentation](https://docs.arduino.cc/hardware/nano/)
- [Arduino Nano Every documentation](https://docs.arduino.cc/hardware/nano-every/)

Profile changes that alter pin meaning are compatibility-significant and must
include a conformance test.
