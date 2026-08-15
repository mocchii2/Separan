import contextlib
from dataclasses import replace
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
TEST_TEMP_ROOT = ROOT / "build" / "test-temp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


@contextlib.contextmanager
def temporary_directory():
    path = TEST_TEMP_ROOT / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)

from separan.capabilities import RuntimeCapabilities
from separan.cli import execute, main
from separan.embedded import BOARD_PROFILES, ValidationEmbeddedAdapter
from separan.embedded import validate_embedded_program
from separan.embedded_firmware import build_pico_project, flash_uf2, generate_pico_project
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser


class EmbeddedBoardTests(unittest.TestCase):
    def test_tier_one_profiles_have_distinct_hardware_metadata(self):
        self.assertEqual(set(BOARD_PROFILES), {
            "raspberry_pi_pico", "raspberry_pi_pico_w", "raspberry_pi_pico_2", "raspberry_pi_pico_2_w",
            "arduino_nano", "arduino_nano_every",
        })
        self.assertEqual(BOARD_PROFILES["raspberry_pi_pico"].mcu, "RP2040")
        self.assertEqual(BOARD_PROFILES["raspberry_pi_pico_2"].mcu, "RP2350")
        self.assertEqual(BOARD_PROFILES["arduino_nano"].mcu, "ATmega328P")
        self.assertEqual(BOARD_PROFILES["arduino_nano_every"].mcu, "ATmega4809")
        self.assertIn("wifi", BOARD_PROFILES["raspberry_pi_pico_w"].features)
        self.assertNotIn("wifi", BOARD_PROFILES["raspberry_pi_pico"].features)

    def test_board_and_pin_queries_are_explicit_and_read_only(self):
        source = '''board = board_select("raspberry_pi_pico")
print board_name()
print board.cpu
print board.voltage
print pin.A0.backend_pin
print pin.A0.physical_pin
print pin_has(pin.D0, "pwm")
print board_has("wifi")
'''
        self.assertEqual(execute(source)[1].splitlines(), [
            "raspberry_pi_pico", "RP2040", "3.3", "GPIO26", "31", "true", "false",
        ])
        with self.assertRaisesRegex(SeparanError, "E215"):
            execute("pin = 1\n")

    def test_pico_w_builtin_led_is_not_falsely_exposed_as_gpio25(self):
        source = '''board = board_select("raspberry_pi_pico_w")
print pin.LED_BUILTIN.backend_pin
print pin_exists("GP25")
'''
        self.assertEqual(execute(source)[1].splitlines(), ["CYW43_WL_GPIO0", "false"])

    def test_pin_requires_selected_board_and_capability(self):
        with self.assertRaisesRegex(SeparanError, "E960"):
            execute("print pin.D0\n")
        with self.assertRaisesRegex(SeparanError, "E962"):
            execute('board = board_select("arduino_nano")\nfunction:main\nanalog_read(pin.D8)\nend_function:main\n')
        output = execute('board = board_select("arduino_nano")\nprint pin_has(pin.A6, "digital_output")\n')[1]
        self.assertEqual(output, "false\n")

    def test_backend_boundary_and_valid_default_buses(self):
        adapter = ValidationEmbeddedAdapter()
        capabilities = replace(RuntimeCapabilities.local(ROOT), embedded_io=True,
                               embedded_boards=frozenset({"raspberry_pi_pico"}))
        source = '''board = board_select("raspberry_pi_pico")
function:main
gpio_set_mode(pin.LED_BUILTIN, "output")
gpio_write(pin.LED_BUILTIN, true)
i2c = i2c_open(0)
print i2c.kind
print i2c.index
end_function:main
'''
        output = execute(source, capabilities=capabilities, embedded_adapter=adapter)[1]
        self.assertEqual(output.splitlines(), ["i2c", "0"])
        self.assertEqual([item[0] for item in adapter.operations], ["gpio_set_mode", "gpio_write", "i2c_open"])
        denied = replace(capabilities, embedded_boards=frozenset({"arduino_nano"}))
        with self.assertRaisesRegex(SeparanError, "E720"):
            execute('board = board_select("raspberry_pi_pico")\nfunction:main\ngpio_read(pin.D0)\nend_function:main\n', capabilities=denied, embedded_adapter=adapter)

    def test_bus_route_must_match_peripheral_instance(self):
        adapter = ValidationEmbeddedAdapter()
        capabilities = replace(RuntimeCapabilities.local(ROOT), embedded_io=True)
        source = 'board = board_select("raspberry_pi_pico")\nfunction:main\ni2c_open(0, sda = pin.D2, scl = pin.D3)\nend_function:main\n'
        with self.assertRaisesRegex(SeparanError, "E963"):
            execute(source, capabilities=capabilities, embedded_adapter=adapter)

    def test_delay_i2c_probe_and_uart_use_the_same_adapter_boundary(self):
        adapter = ValidationEmbeddedAdapter()
        capabilities = replace(RuntimeCapabilities.local(ROOT), embedded_io=True)
        source = '''board = board_select("arduino_nano")
function:main
delay_milliseconds(500)
i2c = i2c_open(0)
print i2c_probe(i2c, 42)
serial = uart_open(0)
uart_write(serial, "hello")
print uart_read_line(serial)
print number_range(1, 4)
end_function:main
'''
        output = execute(source, capabilities=capabilities, embedded_adapter=adapter)[1]
        self.assertEqual(output.splitlines(), ["false", "", "[1, 2, 3]"])
        self.assertEqual([item[0] for item in adapter.operations], [
            "delay_milliseconds", "i2c_open", "i2c_probe", "uart_open", "uart_write", "uart_read_line",
        ])

    def test_build_validates_unexecuted_function_pin_references(self):
        path = ROOT / "tests" / "fixtures" / "embedded_bad_pin.sep"
        stdout, stderr = StringIO(), StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["build", str(path), "--board", "arduino_nano"])
        self.assertEqual(result, 1)
        self.assertIn("E962", stderr.getvalue())

        path = ROOT / "tests" / "fixtures" / "embedded_blink.sep"
        stdout, stderr = StringIO(), StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["build", str(path), "--board", "raspberry_pi_pico_w", "--validate-only"])
        self.assertEqual(result, 0)
        self.assertIn("validation complete", stdout.getvalue())

    def test_pico_and_pico2_emit_official_sdk_projects(self):
        path = ROOT / "examples" / "embedded" / "01_blink.sep"
        source = path.read_text(encoding="utf-8")
        program = Parser(Lexer(source, str(path)).scan_tokens()).parse()
        with temporary_directory() as temporary:
            root = Path(temporary)
            pico = generate_pico_project(program, source, path, "raspberry_pi_pico", root / "pico")
            pico2 = generate_pico_project(program, source, path, "raspberry_pi_pico_2", root / "pico2")
            self.assertEqual((pico.sdk_board, pico2.sdk_board), ("pico", "pico2"))
            self.assertIn("set(PICO_BOARD pico ", pico.cmake_file.read_text(encoding="utf-8"))
            self.assertIn("set(PICO_BOARD pico2 ", pico2.cmake_file.read_text(encoding="utf-8"))
            generated = pico.source_file.read_text(encoding="utf-8")
            self.assertIn("sep_gpio_set_mode(25, SEP_GPIO_OUTPUT);", generated)
            self.assertIn("sep_delay_milliseconds(500);", generated)
            manifest = pico.manifest_file.read_text(encoding="utf-8")
            self.assertIn('"pico_sdk_board": "pico"', manifest)

    def test_all_portable_samples_generate_for_pico_and_pico2(self):
        paths = sorted((ROOT / "examples" / "embedded").glob("*.sep"))
        with temporary_directory() as temporary:
            for board_id in ("raspberry_pi_pico", "raspberry_pi_pico_2"):
                for path in paths:
                    with self.subTest(board=board_id, example=path.name):
                        source = path.read_text(encoding="utf-8")
                        program = Parser(Lexer(source, str(path)).scan_tokens()).parse()
                        project = generate_pico_project(program, source, path, board_id,
                                                        Path(temporary) / board_id / path.stem)
                        self.assertTrue(project.source_file.is_file())

    def test_firmware_matrix_generates_every_supported_pico_api(self):
        path = ROOT / "tests" / "fixtures" / "pico_firmware_matrix.sep"
        source = path.read_text(encoding="utf-8")
        program = Parser(Lexer(source, str(path)).scan_tokens()).parse()
        with temporary_directory() as temporary:
            project = generate_pico_project(program, source, path, "raspberry_pi_pico_2", Path(temporary))
            generated = project.source_file.read_text(encoding="utf-8")
        for symbol in ("sep_gpio_set_mode", "sep_gpio_write", "sep_gpio_read", "sep_pwm_write",
                       "sep_analog_read", "sep_i2c_open", "sep_i2c_probe", "sep_uart_open",
                       "sep_uart_write", "sep_uart_read_line", "sep_delay_milliseconds"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, generated)
        self.assertIn("sep_fn_blink_once();", generated)

    def test_other_board_profiles_do_not_claim_a_firmware_backend(self):
        source = "function:main\nend_function:main\n"
        program = Parser(Lexer(source).scan_tokens()).parse()
        with temporary_directory() as temporary:
            with self.assertRaisesRegex(SeparanError, "E966"):
                generate_pico_project(program, source, Path("main.sep"), "arduino_nano", Path(temporary))

    def test_sdk_builder_uses_direct_process_arguments_and_requires_artifacts(self):
        source = "function:main\nend_function:main\n"
        program = Parser(Lexer(source).scan_tokens()).parse()
        with temporary_directory() as temporary:
            root = Path(temporary)
            project = generate_pico_project(program, source, Path("main.sep"), "raspberry_pi_pico_2", root / "project")
            sdk = root / "sdk"
            (sdk / "external").mkdir(parents=True)
            (sdk / "pico_sdk_init.cmake").write_text("", encoding="utf-8")
            (sdk / "external" / "pico_sdk_import.cmake").write_text("", encoding="utf-8")
            cmake = root / "cmake.exe"
            ninja = root / "ninja.exe"
            cmake.write_bytes(b"")
            ninja.write_bytes(b"")
            build = project.directory / "build"
            build.mkdir()
            for suffix in ("elf", "uf2", "hex", "bin"):
                (build / f"{project.target_name}.{suffix}").write_bytes(suffix.encode("ascii"))
            completed = subprocess.CompletedProcess([], 0, "", "")
            with mock.patch("separan.embedded_firmware.subprocess.run", return_value=completed) as run:
                artifacts = build_pico_project(project, sdk_path=sdk, cmake=cmake, ninja=ninja)
            self.assertEqual(artifacts.uf2.read_bytes(), b"uf2")
            self.assertEqual(run.call_count, 2)
            configure = run.call_args_list[0].args[0]
            self.assertIn("-DPICO_BOARD=pico2", configure)
            self.assertNotIsInstance(configure, str)

    def test_flash_requires_explicit_uf2_device_marker(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            image = root / "blink.uf2"
            image.write_bytes(b"firmware")
            device = root / "device"
            device.mkdir()
            with self.assertRaisesRegex(SeparanError, "E969"):
                flash_uf2(image, device)
            (device / "INFO_UF2.TXT").write_text("UF2 Bootloader v3.0\nBoard-ID: RPI-RP2\n", encoding="utf-8")
            destination = flash_uf2(image, device)
            self.assertEqual(destination.read_bytes(), b"firmware")

    def test_cli_emit_only_writes_project_without_sdk(self):
        path = ROOT / "tests" / "fixtures" / "embedded_blink.sep"
        with temporary_directory() as temporary:
            stdout, stderr = StringIO(), StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["build", str(path), "--board", "raspberry_pi_pico_2",
                               "--emit-only", "--output-dir", temporary])
            self.assertEqual(result, 0, stderr.getvalue())
            self.assertTrue((Path(temporary) / "separan_firmware.cpp").is_file())
            self.assertIn("Pico SDK board: pico2", stdout.getvalue())

    def test_build_target_cannot_be_overridden_by_source(self):
        with self.assertRaisesRegex(SeparanError, "E960"):
            execute('board = board_select("arduino_nano")\n', board_id="raspberry_pi_pico")

    def test_static_validator_rejects_literal_hardware_mistakes(self):
        cases = (
            ('function:main\ngpio_set_mode(pin.D0, "maybe")\nend_function:main\n', "E965"),
            ('function:main\ngpio_write(pin.D0, 1)\nend_function:main\n', "E201"),
            ('function:main\npwm_write(pin.D3, 2)\nend_function:main\n', "E965"),
            ('function:main\ni2c_open(-1)\nend_function:main\n', "E963"),
            ('function:main\ndelay_milliseconds(-1)\nend_function:main\n', "E965"),
            ('function:main\ni2c_probe(bus, 128)\nend_function:main\n', "E965"),
            ('function:main\nled = pin.D8\nanalog_read(led)\nend_function:main\n', "E962"),
            ('function:main\nanalog_read(sensor)\nend_function:main\nsensor = pin.D8\n', "E962"),
        )
        for source, code in cases:
            with self.subTest(code=code, source=source):
                program = Parser(Lexer(source).scan_tokens()).parse()
                with self.assertRaisesRegex(SeparanError, code):
                    validate_embedded_program(program, "arduino_nano")

    def test_official_embedded_samples_validate_for_every_tier_one_board(self):
        paths = sorted((ROOT / "examples" / "embedded").glob("*.sep"))
        self.assertEqual(len(paths), 7)
        for path in paths:
            program = Parser(Lexer(path.read_text(encoding="utf-8"), str(path)).scan_tokens()).parse()
            for board_id in BOARD_PROFILES:
                with self.subTest(example=path.name, board=board_id):
                    validate_embedded_program(program, board_id)


if __name__ == "__main__":
    unittest.main()
