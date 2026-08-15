# Separan Embedded Board Mapping Specification — preview v0.1

Status: **experimental reference implementation**. Logical board profiles,
capability validation, static `build --board` validation, and a host-adapter
boundary are implemented. Firmware generation and Arduino Core/Pico SDK
adapters are not yet included.

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
separan build examples/embedded_blink.sep --board raspberry_pi_pico
```

The current `build` command parses the complete program and validates every
direct `pin.NAME` reference, including references in functions that are not
executed. It deliberately reports that it performs mapping validation only.
It does not claim to emit firmware.

## Implemented Tier 1 profiles

| Profile ID | Family | MCU | Logic | Wireless |
|---|---|---|---:|---|
| `raspberry_pi_pico` | Raspberry Pi Pico | RP2040 | 3.3 V | no |
| `raspberry_pi_pico_w` | Raspberry Pi Pico | RP2040 | 3.3 V | Wi-Fi, Bluetooth |
| `raspberry_pi_pico_2` | Raspberry Pi Pico | RP2350 | 3.3 V | no |
| `raspberry_pi_pico_2_w` | Raspberry Pi Pico | RP2350 | 3.3 V | Wi-Fi, Bluetooth |
| `arduino_nano` | Arduino Nano | ATmega328P | 5 V | no |
| `arduino_nano_every` | Arduino Nano | ATmega4809 | 5 V | no |

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

`analog_write` exists as a capability-checked contract; none of the current
Tier 1 profiles advertises a true DAC output. `pwm_write` is the explicit PWM
operation. Analog and PWM output values use the closed range 0 through 1.

Bus index and signal role must match the selected peripheral instance. A pin
that can act as I²C1 SDA is not silently accepted as I²C0 SDA. Omitting pin
arguments uses the profile's deterministic default bus mapping.

Hardware operations require the host's `embedded_io` capability and may be
restricted to an `embedded_boards` allowlist. They then call a supplied adapter.
The Python reference interpreter ships only a side-effect-free validation
adapter; direct register access and shell-command fallbacks are forbidden.

## Diagnostics

| Code | Meaning |
|---|---|
| `E960` | board missing, unknown, or different from locked build target |
| `E961` | unknown pin or pin from a different profile |
| `E962` | requested pin capability is unavailable |
| `E963` | bus signal and peripheral instance do not form a valid mapping |
| `E964` | adapter missing, failed, or returned the wrong type |
| `E965` | invalid GPIO mode or analog/PWM value |

## Hardware data sources

Profiles are derived from vendor documentation, not community pin tables:

- [Raspberry Pi Pico-series documentation and pinout files](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [Raspberry Pi Pico SDK hardware APIs](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html)
- [Arduino Nano documentation](https://docs.arduino.cc/hardware/nano/)
- [Arduino Nano Every documentation](https://docs.arduino.cc/hardware/nano-every/)

Profile changes that alter pin meaning are compatibility-significant and must
include a conformance test.
