"""Strict logical-pin board profiles and the embedded host-adapter boundary."""

from dataclasses import dataclass, fields, is_dataclass

from .ast_nodes import CallExpr, LiteralExpr, MemberExpr, UnaryExpr, VariableExpr
from .errors import error
from .system_utilities import UtilityFunction


DIGITAL = ("digital_input", "digital_output")


@dataclass(frozen=True)
class PinDefinition:
    name: str
    physical_pin: int | str
    backend_pin: str
    voltage: float
    capabilities: tuple[str, ...]
    routes: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class BoardProfile:
    id: str
    display_name: str
    family: str
    mcu: str
    logic_voltage: float
    flash_bytes: int
    ram_bytes: int
    features: tuple[str, ...]
    pins: dict[str, PinDefinition]
    aliases: dict[str, str]
    default_buses: dict[tuple[str, int], dict[str, str]]

    def resolve(self, name, position):
        canonical = self.aliases.get(name, name)
        pin = self.pins.get(canonical)
        if pin is None:
            raise error("E961", "Unknown board pin", f"Board '{self.id}' has no logical pin '{name}'.", position,
                        expected="one of: " + ", ".join(sorted(self.aliases)), actual=name)
        return PinValue(self.id, pin)


@dataclass(frozen=True)
class BoardValue:
    profile: BoardProfile


@dataclass(frozen=True)
class PinValue:
    board_id: str
    definition: PinDefinition


@dataclass(frozen=True)
class BusValue:
    board_id: str
    kind: str
    index: int
    pins: tuple[PinValue, ...]


@dataclass(frozen=True)
class PinNamespaceValue:
    context: object


class EmbeddedContext:
    def __init__(self, board_id=None, *, locked=False, adapter=None):
        self.profile = None
        self.locked = locked
        self.adapter = adapter
        if board_id is not None:
            self.select(board_id, None)

    def select(self, board_id, position):
        profile = BOARD_PROFILES.get(board_id)
        if profile is None:
            raise error("E960", "Unknown board profile", f"Board profile '{board_id}' is not available.", _position(position),
                        expected="one of: " + ", ".join(sorted(BOARD_PROFILES)), actual=board_id)
        if self.locked and self.profile is not None and self.profile.id != board_id:
            raise error("E960", "Board target mismatch", "Source selection cannot override the build target.", _position(position),
                        expected=self.profile.id, actual=board_id)
        self.profile = profile
        return BoardValue(profile)

    def require_profile(self, position):
        if self.profile is None:
            raise error("E960", "Board is not selected", "Select a board with board_select() or --board before using pin values.", position)
        return self.profile

    def resolve(self, value, position):
        profile = self.require_profile(position)
        if isinstance(value, PinValue):
            if value.board_id != profile.id:
                raise error("E961", "Pin belongs to another board", "A pin value cannot cross board profiles.", position,
                            expected=profile.id, actual=value.board_id)
            return value
        if type(value) is str:
            return profile.resolve(value, position)
        raise error("E201", "Type error", "A logical pin value or pin name is required.", position,
                    expected="pin or string", actual=type(value).__name__)

    def perform(self, operation, payload, position, runtime):
        runtime.capabilities.require(runtime.capabilities.embedded_io, "embedded hardware I/O", position)
        allowed = runtime.capabilities.embedded_boards
        profile = self.require_profile(position)
        if allowed is not None and profile.id not in allowed:
            raise error("E720", "Permission error", f"Board '{profile.id}' is outside the host allowlist.", position, actual=profile.id)
        if self.adapter is None:
            raise error("E964", "Embedded backend unavailable", "No embedded host adapter is attached to this interpreter.", position,
                        actual=operation)
        try:
            return self.adapter.perform(operation, payload)
        except Exception as exc:
            if getattr(exc, "code", None):
                raise
            raise error("E964", "Embedded backend error", str(exc), position, actual=operation)


class ValidationEmbeddedAdapter:
    """Side-effect-free build validator; it never accesses physical hardware."""

    def __init__(self):
        self.operations = []

    def perform(self, operation, payload):
        self.operations.append((operation, payload))
        if operation == "gpio_read": return False
        if operation == "analog_read": return 0
        return None


def _position(position):
    if position is not None: return position
    from .token import SourcePosition
    return SourcePosition("<board>", 1, 1, "")


def _pin(name, physical, backend, voltage, capabilities, routes=()):
    return PinDefinition(name, physical, backend, voltage, tuple(dict.fromkeys(capabilities)), tuple(routes))


def _pico_profile(board_id, display_name, mcu, flash, ram, wireless=False):
    pins = {}
    physical = {0: 1, 1: 2, 2: 4, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 11, 9: 12,
                10: 14, 11: 15, 12: 16, 13: 17, 14: 19, 15: 20, 16: 21, 17: 22,
                18: 24, 19: 25, 20: 26, 21: 27, 22: 29, 26: 31, 27: 32, 28: 34}
    i2c0_sda = {0, 4, 8, 12, 16, 20}; i2c0_scl = {1, 5, 9, 13, 17, 21}
    i2c1_sda = {2, 6, 10, 14, 18, 26}; i2c1_scl = {3, 7, 11, 15, 19, 27}
    spi0 = {"spi_miso": {0, 4, 16, 20}, "spi_chip_select": {1, 5, 17, 21},
            "spi_clock": {2, 6, 18, 22}, "spi_mosi": {3, 7, 19}}
    spi1 = {"spi_miso": {8, 12, 28}, "spi_chip_select": {9, 13},
            "spi_clock": {10, 14, 26}, "spi_mosi": {11, 15, 27}}
    uart0 = {"uart_tx": {0, 12, 16, 28}, "uart_rx": {1, 13, 17}}
    uart1 = {"uart_tx": {4, 8, 20}, "uart_rx": {5, 9, 21}}
    for number, physical_pin in physical.items():
        caps = [*DIGITAL, "pwm"]
        routes = []
        for capability, values, instance in (
            ("i2c_sda", i2c0_sda, 0), ("i2c_scl", i2c0_scl, 0),
            ("i2c_sda", i2c1_sda, 1), ("i2c_scl", i2c1_scl, 1),
        ):
            if number in values: caps.append(capability); routes.append((capability, instance))
        for instance, table in ((0, spi0), (1, spi1)):
            for capability, values in table.items():
                if number in values: caps.append(capability); routes.append((capability, instance))
        for instance, table in ((0, uart0), (1, uart1)):
            for capability, values in table.items():
                if number in values: caps.append(capability); routes.append((capability, instance))
        if number in (26, 27, 28): caps.append("analog_input")
        pins[f"GP{number}"] = _pin(f"GP{number}", physical_pin, f"GPIO{number}", 3.3, caps, routes)
    led_backend = "CYW43_WL_GPIO0" if wireless else "GPIO25"
    pins["LED_BUILTIN"] = _pin("LED_BUILTIN", "on-board", led_backend, 3.3, DIGITAL)
    aliases = {name: name for name in pins}
    aliases.update({f"D{number}": f"GP{number}" for number in range(23)})
    aliases.update({"A0": "GP26", "A1": "GP27", "A2": "GP28", "SDA": "GP4", "SCL": "GP5",
                    "TX": "GP0", "RX": "GP1", "MISO": "GP16", "CS": "GP17", "SCK": "GP18", "MOSI": "GP19"})
    features = ["usb", "adc", "pwm", "i2c", "spi", "uart"]
    if wireless: features += ["wifi", "bluetooth"]
    defaults = {
        ("i2c", 0): {"sda": "GP4", "scl": "GP5"},
        ("spi", 0): {"miso": "GP16", "chip_select": "GP17", "clock": "GP18", "mosi": "GP19"},
        ("uart", 0): {"tx": "GP0", "rx": "GP1"},
    }
    return BoardProfile(board_id, display_name, "raspberry_pi_pico", mcu, 3.3, flash, ram,
                        tuple(features), pins, aliases, defaults)


def _nano_profile(board_id, display_name, mcu, flash, ram, every=False):
    pins = {}
    physical = {0: 2, 1: 1, 2: 5, 3: 6, 4: 7, 5: 8, 6: 9, 7: 10,
                8: 11, 9: 12, 10: 13, 11: 14, 12: 15, 13: 16}
    pwm = {3, 5, 6, 9, 10} if every else {3, 5, 6, 9, 10, 11}
    for number, physical_pin in physical.items():
        caps = [*DIGITAL]
        routes = []
        if number in pwm: caps.append("pwm")
        for capability, member in (("uart_rx", 0), ("uart_tx", 1), ("spi_chip_select", 10),
                                   ("spi_mosi", 11), ("spi_miso", 12), ("spi_clock", 13)):
            if number == member: caps.append(capability); routes.append((capability, 0))
        pins[f"D{number}"] = _pin(f"D{number}", physical_pin, f"D{number}", 5.0, caps, routes)
    for number in range(8):
        caps = ["analog_input"]
        if every or number <= 5: caps += [*DIGITAL]
        routes = []
        if number == 4: caps.append("i2c_sda"); routes.append(("i2c_sda", 0))
        if number == 5: caps.append("i2c_scl"); routes.append(("i2c_scl", 0))
        pins[f"A{number}"] = _pin(f"A{number}", 19 + number, f"A{number}", 5.0, caps, routes)
    aliases = {name: name for name in pins}
    aliases.update({"SDA": "A4", "SCL": "A5", "RX": "D0", "TX": "D1", "CS": "D10",
                    "MOSI": "D11", "MISO": "D12", "SCK": "D13", "LED_BUILTIN": "D13"})
    defaults = {
        ("i2c", 0): {"sda": "A4", "scl": "A5"},
        ("spi", 0): {"chip_select": "D10", "mosi": "D11", "miso": "D12", "clock": "D13"},
        ("uart", 0): {"rx": "D0", "tx": "D1"},
    }
    return BoardProfile(board_id, display_name, "arduino_nano", mcu, 5.0, flash, ram,
                        ("usb", "adc", "pwm", "i2c", "spi", "uart"), pins, aliases, defaults)


BOARD_PROFILES = {
    profile.id: profile for profile in (
        _pico_profile("raspberry_pi_pico", "Raspberry Pi Pico", "RP2040", 2 * 1024**2, 264 * 1024),
        _pico_profile("raspberry_pi_pico_w", "Raspberry Pi Pico W", "RP2040", 2 * 1024**2, 264 * 1024, True),
        _pico_profile("raspberry_pi_pico_2", "Raspberry Pi Pico 2", "RP2350", 4 * 1024**2, 520 * 1024),
        _pico_profile("raspberry_pi_pico_2_w", "Raspberry Pi Pico 2 W", "RP2350", 4 * 1024**2, 520 * 1024, True),
        _nano_profile("arduino_nano", "Arduino Nano", "ATmega328P", 32 * 1024, 2 * 1024),
        _nano_profile("arduino_nano_every", "Arduino Nano Every", "ATmega4809", 48 * 1024, 6 * 1024, True),
    )
}


def pin_member(namespace, name, position):
    return namespace.context.require_profile(position).resolve(name, position)


def fixed_member(value, name, position):
    if isinstance(value, BoardValue):
        p = value.profile
        members = {"id": p.id, "name": p.display_name, "family": p.family, "cpu": p.mcu,
                   "voltage": p.logic_voltage, "flash_bytes": p.flash_bytes, "ram_bytes": p.ram_bytes,
                   "features": list(p.features)}
    elif isinstance(value, PinValue):
        p = value.definition
        members = {"name": p.name, "physical_pin": p.physical_pin, "backend_pin": p.backend_pin,
                   "voltage": p.voltage, "capabilities": list(p.capabilities)}
    elif isinstance(value, BusValue):
        members = {"board": value.board_id, "kind": value.kind, "index": value.index,
                   "pins": list(value.pins)}
    else:
        return None, False
    if name not in members:
        raise error("E212", "Missing embedded field", f"{type(value).__name__} has no field '{name}'.", position, actual=name)
    return members[name], True


def _string(value, name, position, runtime):
    if type(value) is not str: runtime.type_error(position, "string", runtime.type_name(value), f"{name} must be a string.")


def _context(runtime): return runtime.embedded_context


def _board_select(args, named, position, runtime):
    _string(args[0], "board id", position, runtime)
    return _context(runtime).select(args[0], position)


def _profile(runtime, position): return _context(runtime).require_profile(position)


def _board_field(field):
    def implementation(args, named, position, runtime): return getattr(_profile(runtime, position), field)
    return implementation


def _board_has(args, named, position, runtime):
    _string(args[0], "feature", position, runtime)
    return args[0] in _profile(runtime, position).features


def _board_pins(args, named, position, runtime): return sorted(_profile(runtime, position).aliases)
def _board_features(args, named, position, runtime): return list(_profile(runtime, position).features)


def _pin_exists(args, named, position, runtime):
    _string(args[0], "pin name", position, runtime); p = _profile(runtime, position)
    return args[0] in p.aliases or args[0] in p.pins


def _pin_has(args, named, position, runtime):
    pin = _context(runtime).resolve(args[0], position); _string(args[1], "capability", position, runtime)
    return args[1] in pin.definition.capabilities


def _pin_capabilities(args, named, position, runtime):
    return list(_context(runtime).resolve(args[0], position).definition.capabilities)


def _require_pin(runtime, value, capability, position):
    pin = _context(runtime).resolve(value, position)
    if capability not in pin.definition.capabilities:
        raise error("E962", "Pin capability mismatch", f"Pin '{pin.definition.name}' does not support {capability}.", position,
                    expected=capability, actual=", ".join(pin.definition.capabilities))
    return pin


def _gpio_set_mode(args, named, position, runtime):
    pin, mode = args; _string(mode, "GPIO mode", position, runtime)
    modes = {"input": "digital_input", "input_pull_up": "digital_input", "input_pull_down": "digital_input", "output": "digital_output"}
    if mode not in modes: raise error("E965", "Invalid GPIO mode", "GPIO mode must be input, input_pull_up, input_pull_down, or output.", position, actual=mode)
    value = _require_pin(runtime, pin, modes[mode], position)
    return _context(runtime).perform("gpio_set_mode", {"pin": value, "mode": mode}, position, runtime)


def _gpio_write(args, named, position, runtime):
    pin, value = args
    if type(value) is not bool: runtime.type_error(position, "boolean", runtime.type_name(value), "gpio_write() value must be boolean.")
    pin = _require_pin(runtime, pin, "digital_output", position)
    return _context(runtime).perform("gpio_write", {"pin": pin, "value": value}, position, runtime)


def _gpio_read(args, named, position, runtime):
    pin = _require_pin(runtime, args[0], "digital_input", position)
    value = _context(runtime).perform("gpio_read", {"pin": pin}, position, runtime)
    if type(value) is not bool: raise error("E964", "Embedded backend error", "gpio_read backend must return boolean.", position)
    return value


def _analog_read(args, named, position, runtime):
    pin = _require_pin(runtime, args[0], "analog_input", position)
    value = _context(runtime).perform("analog_read", {"pin": pin}, position, runtime)
    if type(value) not in (int, float) or type(value) is bool: raise error("E964", "Embedded backend error", "analog_read backend must return number.", position)
    return value


def _analog_write(args, named, position, runtime):
    pin, value = args
    if type(value) not in (int, float) or type(value) is bool or not 0 <= value <= 1:
        raise error("E965", "Invalid analog output value", "analog_write() value must be a number from 0 through 1.", position, expected="0..1", actual=repr(value))
    pin = _require_pin(runtime, pin, "analog_output", position)
    return _context(runtime).perform("analog_write", {"pin": pin, "value": value}, position, runtime)


def _pwm_write(args, named, position, runtime):
    pin, value = args
    if type(value) not in (int, float) or type(value) is bool or not 0 <= value <= 1:
        raise error("E965", "Invalid PWM duty cycle", "pwm_write() duty cycle must be a number from 0 through 1.", position, expected="0..1", actual=repr(value))
    pin = _require_pin(runtime, pin, "pwm", position)
    return _context(runtime).perform("pwm_write", {"pin": pin, "value": value}, position, runtime)


BUS_ROLES = {
    "i2c": ("sda", "scl"),
    "spi": ("mosi", "miso", "clock", "chip_select"),
    "uart": ("tx", "rx"),
}


def _bus_open(kind):
    def implementation(args, named, position, runtime):
        index = args[0] if args else 0
        if type(index) is not int or index < 0: runtime.type_error(position, "non-negative integer bus index", runtime.type_name(index), f"{kind}_open() bus index must be a non-negative integer.")
        profile = _profile(runtime, position); mapping = dict(profile.default_buses.get((kind, index), {}))
        mapping.update(named)
        roles = BUS_ROLES[kind]
        missing = [role for role in roles if role not in mapping]
        if missing: raise error("E963", "Missing bus pin mapping", f"{kind.upper()} bus {index} has no mapping for {', '.join(missing)}.", position)
        values = []
        for role in roles:
            pin = _require_pin(runtime, mapping[role], f"{kind}_{role}", position)
            if (f"{kind}_{role}", index) not in pin.definition.routes:
                raise error("E963", f"Invalid {kind.upper()} pin mapping", f"Pin '{pin.definition.name}' cannot be {role} on {kind.upper()} bus {index}.", position,
                            expected=f"{kind}_{role} on bus {index}", actual=pin.definition.name)
            values.append(pin)
        bus = BusValue(profile.id, kind, index, tuple(values))
        _context(runtime).perform(f"{kind}_open", {"bus": bus}, position, runtime)
        return bus
    return implementation


EMBEDDED_BUILTINS = (
    UtilityFunction("board_select", 1, 1, _board_select),
    UtilityFunction("board_name", 0, 0, _board_field("id")),
    UtilityFunction("board_family", 0, 0, _board_field("family")),
    UtilityFunction("board_cpu", 0, 0, _board_field("mcu")),
    UtilityFunction("board_voltage", 0, 0, _board_field("logic_voltage")),
    UtilityFunction("board_has", 1, 1, _board_has),
    UtilityFunction("board_pins", 0, 0, _board_pins),
    UtilityFunction("board_features", 0, 0, _board_features),
    UtilityFunction("pin_exists", 1, 1, _pin_exists),
    UtilityFunction("pin_has", 2, 2, _pin_has),
    UtilityFunction("pin_capabilities", 1, 1, _pin_capabilities),
    UtilityFunction("gpio_set_mode", 2, 2, _gpio_set_mode),
    UtilityFunction("gpio_write", 2, 2, _gpio_write),
    UtilityFunction("gpio_read", 1, 1, _gpio_read),
    UtilityFunction("analog_read", 1, 1, _analog_read),
    UtilityFunction("analog_write", 2, 2, _analog_write),
    UtilityFunction("pwm_write", 2, 2, _pwm_write),
    UtilityFunction("i2c_open", 0, 1, _bus_open("i2c"), ("sda", "scl")),
    UtilityFunction("spi_open", 0, 1, _bus_open("spi"), ("mosi", "miso", "clock", "chip_select")),
    UtilityFunction("uart_open", 0, 1, _bus_open("uart"), ("tx", "rx")),
)


def validate_embedded_program(program, board_id):
    """Validate direct pin references and literal bus mappings without running user code."""
    profile = BOARD_PROFILES.get(board_id)
    if profile is None:
        raise error("E960", "Unknown board profile", f"Board profile '{board_id}' is not available.", program.position,
                    expected="one of: " + ", ".join(sorted(BOARD_PROFILES)), actual=board_id)

    def direct_pin(expression):
        if isinstance(expression, MemberExpr) and isinstance(expression.target, VariableExpr) and expression.target.name == "pin":
            return profile.resolve(expression.name, expression.position)
        return None

    unknown = object()
    def literal_value(expression):
        if isinstance(expression, LiteralExpr): return expression.value
        if isinstance(expression, UnaryExpr) and expression.operator == "-" and isinstance(expression.operand, LiteralExpr):
            value = expression.operand.value
            if type(value) in (int, float) and type(value) is not bool: return -value
        return unknown

    def walk(value):
        if isinstance(value, MemberExpr): direct_pin(value)
        if isinstance(value, CallExpr):
            if value.callee == "board_select" and value.arguments and isinstance(value.arguments[0], LiteralExpr):
                selected = value.arguments[0].value
                if selected != board_id:
                    raise error("E960", "Board target mismatch", "Source selection does not match --board.", value.position,
                                expected=board_id, actual=str(selected))
            requirements = {"gpio_set_mode": None, "gpio_write": "digital_output", "gpio_read": "digital_input",
                            "analog_read": "analog_input", "analog_write": "analog_output", "pwm_write": "pwm"}
            if value.callee in requirements and value.arguments:
                pin = direct_pin(value.arguments[0])
                required = requirements[value.callee]
                if pin and value.callee == "gpio_set_mode" and len(value.arguments) > 1 and isinstance(value.arguments[1], LiteralExpr):
                    mode = value.arguments[1].value
                    required = {"output": "digital_output", "input": "digital_input", "input_pull_up": "digital_input", "input_pull_down": "digital_input"}.get(mode)
                    if required is None:
                        raise error("E965", "Invalid GPIO mode", "GPIO mode must be input, input_pull_up, input_pull_down, or output.",
                                    value.arguments[1].position, actual=str(mode))
                if pin and required and required not in pin.definition.capabilities:
                    raise error("E962", "Pin capability mismatch", f"Pin '{pin.definition.name}' does not support {required}.", value.position,
                                expected=required, actual=", ".join(pin.definition.capabilities))
                if value.callee == "gpio_write" and len(value.arguments) > 1 and isinstance(value.arguments[1], LiteralExpr) and type(value.arguments[1].value) is not bool:
                    raise error("E201", "Type error", "gpio_write() value must be boolean.", value.arguments[1].position,
                                expected="boolean", actual=type(value.arguments[1].value).__name__)
                if value.callee in ("analog_write", "pwm_write") and len(value.arguments) > 1 and isinstance(value.arguments[1], LiteralExpr):
                    output = value.arguments[1].value
                    if type(output) not in (int, float) or type(output) is bool or not 0 <= output <= 1:
                        raise error("E965", "Invalid embedded output value", f"{value.callee}() value must be a number from 0 through 1.",
                                    value.arguments[1].position, expected="0..1", actual=repr(output))
            if value.callee in {f"{name}_open" for name in BUS_ROLES}:
                kind = value.callee[:-5] if value.callee.endswith("_open") else value.callee
                index = literal_value(value.arguments[0]) if value.arguments else 0
                if index is not unknown and (type(index) is not int or index < 0):
                    raise error("E963", "Invalid bus index", "Bus index must be a non-negative integer literal.", value.position,
                                expected="non-negative integer", actual=repr(index))
                defaults = profile.default_buses.get((kind, index), {}) if type(index) is int else {}
                for role, expression in value.named_arguments.items():
                    pin = direct_pin(expression)
                    if pin and index is not unknown and (f"{kind}_{role}", index) not in pin.definition.routes:
                        raise error("E963", f"Invalid {kind.upper()} pin mapping", f"Pin '{pin.definition.name}' cannot be {role} on {kind.upper()} bus {index}.", expression.position)
                if index is not unknown and not value.named_arguments and not defaults:
                    raise error("E963", "Missing bus pin mapping", f"{kind.upper()} bus {index} has no default mapping.", value.position)
        if is_dataclass(value):
            for item in fields(value):
                if item.name != "position": walk(getattr(value, item.name))
        elif isinstance(value, (list, tuple)):
            for item in value: walk(item)
        elif isinstance(value, dict):
            for item in value.values(): walk(item)
    walk(program)
    return profile
