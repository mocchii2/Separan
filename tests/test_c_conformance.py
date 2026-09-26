"""Cross implementation checks for the native C parser and runtime."""

import re
import json
import ctypes
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.parser import Parser
from separan.cli import execute
from separan.interpreter import Interpreter
from separan.builtins import BUILTINS


class NativeToken(ctypes.Structure):
    _fields_ = [("type", ctypes.c_char_p), ("lexeme", ctypes.c_char_p),
                ("line", ctypes.c_size_t), ("column", ctypes.c_size_t)]


class NativeTokens(ctypes.Structure):
    _fields_ = [("tokens", ctypes.POINTER(NativeToken)), ("count", ctypes.c_size_t),
                ("error_code", ctypes.c_char * 8), ("error_line", ctypes.c_size_t),
                ("error_column", ctypes.c_size_t)]


class NativeStructureConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc") or shutil.which("clang")
        if compiler is None:
            raise unittest.SkipTest("C compiler unavailable")
        cls._temporary = tempfile.TemporaryDirectory()
        cls.binary = Path(cls._temporary.name) / ("separan.exe" if sys.platform == "win32" else "separan")
        c_root = ROOT / "reference" / "c"
        subprocess.run(
            [compiler, "-O1", "-std=c11", "-Wall", "-Wextra", "-I", str(c_root / "include"),
             str(c_root / "src" / "main.c"), str(c_root / "src" / "separan_core.c"),
             str(c_root / "src" / "separan_lexer.c"), str(c_root / "src" / "separan_files.c"),
             str(c_root / "src" / "separan_runtime.c"),
             "-o", str(cls.binary), "-lm"],
            check=True, capture_output=True, text=True,
        )
        cls.regex_binary = Path(cls._temporary.name) / ("regex-runner.exe" if sys.platform == "win32" else "regex-runner")
        subprocess.run(
            [compiler, "-O1", "-std=c11", "-Wall", "-Wextra", "-I", str(c_root / "include"),
             str(ROOT / "tests" / "c_host_regex_runner.c"), str(c_root / "src" / "separan_core.c"),
             str(c_root / "src" / "separan_lexer.c"), str(c_root / "src" / "separan_files.c"),
             str(c_root / "src" / "separan_runtime.c"), "-o", str(cls.regex_binary), "-lm"],
            check=True, capture_output=True, text=True,
        )
        library = Path(cls._temporary.name) / ("lexer.dll" if sys.platform == "win32" else "lexer.so")
        subprocess.run(
            [compiler, "-O1", "-std=c11", "-Wall", "-Wextra", "-shared", "-fPIC",
             "-I", str(c_root / "include"), str(c_root / "src" / "separan_lexer.c"),
             "-o", str(library)],
            check=True, capture_output=True, text=True,
        )
        cls.lexer = ctypes.CDLL(str(library))
        cls.lexer.separan_lex.argtypes = [ctypes.c_char_p, ctypes.POINTER(NativeTokens)]
        cls.lexer.separan_lex.restype = ctypes.c_int
        cls.lexer.separan_tokens_free.argtypes = [ctypes.POINTER(NativeTokens)]

    @classmethod
    def tearDownClass(cls):
        if sys.platform == "win32":
            import _ctypes
            _ctypes.FreeLibrary(cls.lexer._handle)
        else:
            import _ctypes
            _ctypes.dlclose(cls.lexer._handle)
        cls._temporary.cleanup()

    def test_host_api_registry_matches_python_signatures(self):
        source = (ROOT / "reference" / "c" / "src" / "separan_runtime.c").read_text(encoding="utf-8")
        block = re.search(r"static const HostSignature host_signatures\[\].*?\{(.*?)\n \};", source, re.S)
        self.assertIsNotNone(block)
        rows = re.findall(r'^\s*\{"([a-z][a-z_0-9]*)",(\d+),(\d+),"([^"]*)"\}', block.group(1), re.M)
        actual = {name: (int(minimum), int(maximum), frozenset(filter(None, named.split("|"))))
                  for name, minimum, maximum, named in rows}
        modules = {"network", "network_services", "embedded", "http_client", "http_server",
                   "mail.core", "auth", "cookies", "cookie_store", "structured_data",
                   "crypto_ops", "system_utilities"}
        expected = {}
        native = set(re.findall(r'"([a-z][a-z_0-9]*)"', source[source.index("static int builtin_name"):]))
        native.difference_update(actual)  # Host signatures stay adapter-backed even when results are normalized natively.
        for name, builtin in BUILTINS.items():
            module = getattr(builtin.implementation, "__module__", "").removeprefix("separan.")
            if module in modules and name not in native:
                expected[name] = (builtin.minimum_arguments, builtin.maximum_arguments,
                                  frozenset(getattr(builtin, "named", ())))
        self.assertEqual(actual, expected)

    def test_all_builtin_arity_contracts_match(self):
        checked = 0
        for name, builtin in BUILTINS.items():
            argument_sets = [["0"] * (builtin.maximum_arguments + 1)]
            if builtin.minimum_arguments:
                argument_sets.append(["0"] * (builtin.minimum_arguments - 1))
            for arguments in argument_sets:
                source = f"print {name}({', '.join(arguments)})\n"
                path = Path(self._temporary.name) / f"arity-{name}-{len(arguments)}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                with self.subTest(name=name, arguments=len(arguments)):
                    self.assertNotEqual(actual.returncode, 0)
                    self.assertIn("E207", actual.stderr)
                checked += 1
        self.assertEqual(checked, sum(1 + (builtin.minimum_arguments > 0)
                                      for builtin in BUILTINS.values()))

    def test_all_builtin_unknown_named_arguments_match(self):
        checked = 0
        for name in BUILTINS:
            source = f"print {name}(unexpected = 0)\n"
            path = Path(self._temporary.name) / f"unknown-named-{name}.sep"
            path.write_text(source, encoding="utf-8")
            actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                    text=True, encoding="utf-8")
            with self.subTest(name=name):
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn("E207", actual.stderr)
            checked += 1
        self.assertEqual(checked, len(BUILTINS))

    def test_core_builtin_string_type_errors_match(self):
        source_c = (ROOT / "reference" / "c" / "src" / "separan_runtime.c").read_text(encoding="utf-8")
        block = re.search(r"static const HostSignature host_signatures\[\].*?\{(.*?)\n \};", source_c, re.S)
        self.assertIsNotNone(block)
        host_names = set(re.findall(r'^\s*\{"([a-z][a-z_0-9]*)"', block.group(1), re.M))
        adapter_only = host_names | {"exec", "exec_checked"}
        checked = 0
        for name, builtin in BUILTINS.items():
            if not builtin.minimum_arguments or name in adapter_only:
                continue
            source = f'SEP:main\nprint {name}(' + ", ".join(['"x"'] * builtin.minimum_arguments) + ')\nEND_SEP:main\n'
            try:
                execute(source)
            except SeparanError as caught:
                expected_code = caught.code
            except Exception:
                continue
            else:
                continue
            if expected_code not in ("E201", "E304"):
                continue
            path = Path(self._temporary.name) / f"type-string-{name}.sep"
            path.write_text(source, encoding="utf-8")
            actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                    text=True, encoding="utf-8")
            match = re.search(r"SEPARAN (E\d+):", actual.stderr)
            native_code = match.group(1) if match else None
            with self.subTest(name=name):
                self.assertNotEqual(actual.returncode, 0)
                self.assertEqual(native_code, expected_code, actual.stderr)
            checked += 1
        self.assertGreaterEqual(checked, 160)

    def test_builtin_type_and_value_diagnostics_match(self):
        cases = (
            ('split(true, ",")', "E201"),
            ('split("a", "")', "E305"),
            ('replace("a", true, "b")', "E201"),
            ('replace("a", "", "b")', "E305"),
            ('find_all(true, "a")', "E201"),
            ('find_all("a", "")', "E305"),
            ('local_datetime(true)', "E201"),
            ('local_datetime("bad")', "E404"),
            ('duration(true)', "E201"),
            ('duration("bad")', "E407"),
            ('format(true)', "E201"),
            ('number(true)', "E201"),
            ('timezone(true)', "E201"),
            ('json_decode(true)', "E201"),
        )
        for index, (expression, expected_code) in enumerate(cases):
            source = f"SEP:main\nprint {expression}\nEND_SEP:main\n"
            path = Path(self._temporary.name) / f"builtin-diagnostic-{index}.sep"
            path.write_text(source, encoding="utf-8")
            with self.subTest(expression=expression):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                self.assertEqual(caught.exception.code, expected_code)
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                match = re.search(r"SEPARAN (E\d+):", actual.stderr)
                self.assertNotEqual(actual.returncode, 0)
                self.assertEqual(match.group(1) if match else None, expected_code, actual.stderr)

    def test_namespaced_import_function_constant_and_error(self):
        directory = Path(self._temporary.name) / "modules"
        directory.mkdir()
        module = ('const version = "1"\nerror:math_error\nend_error:math_error\nprint "loaded"\n'
                  'SEP:add(a, b)\nreturn a + b\nEND_SEP:add\n'
                  'SEP:main\nprint "must not run"\nEND_SEP:main\n')
        (directory / "math.sep").write_text(module, encoding="utf-8")
        source = ('import "math.sep" as math\nimport "math.sep" as math_again\nSEP:main\nprint math.add(2, 3)\n'
                  'print math.version\nprint reduce([1, 2, 3], math.add, 0)\ntry :failure\nthrow math.math_error("bad")\n'
                  'catch math_error :failure\nprint "caught"\nendtry:failure\nEND_SEP:main\n')
        caller = directory / "caller.sep"
        caller.write_text(source, encoding="utf-8")
        expected = execute(source, str(caller), script_path=str(caller), project_root=directory)[1]
        actual = subprocess.run([str(self.binary), str(caller)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_nested_imports_and_repeated_calls_match(self):
        directory = Path(self._temporary.name) / "import-load"
        directory.mkdir()
        depth = 40
        for index in range(depth):
            if index + 1 < depth:
                module = (
                    f'import "module_{index + 1}.sep" as child\n'
                    "SEP:value()\nreturn child.value() + 1\nEND_SEP:value\n"
                )
            else:
                module = "SEP:value()\nreturn 1\nEND_SEP:value\n"
            (directory / f"module_{index}.sep").write_text(module, encoding="utf-8")

        source = '''import "module_0.sep" as root
import "module_0.sep" as root_again
SEP:main
iteration = 0
while iteration < 20 :repeat
print root.value() + root_again.value()
iteration = iteration + 1
endwhile:repeat
END_SEP:main
'''
        caller = directory / "caller.sep"
        caller.write_text(source, encoding="utf-8")
        expected = execute(source, str(caller), script_path=str(caller), project_root=directory)[1]
        actual = subprocess.run([str(self.binary), str(caller)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_deep_recursive_calls_match(self):
        source = '''SEP:descend(value: number)
if value == 0 :base
return 0
else:base
return descend(value - 1) + 1
endif:base
END_SEP:descend
SEP:main
print descend(80)
END_SEP:main
'''
        expected = execute(source)[1]
        path = Path(self._temporary.name) / "deep-recursion.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8", timeout=10)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_import_boundaries_match(self):
        directory = Path(self._temporary.name) / "import-errors"
        directory.mkdir()
        (directory / "math.sep").write_text('private_value = 9\nSEP:add(a, b)\nreturn a + b\nEND_SEP:add\n', encoding="utf-8")
        (directory / "throwing.sep").write_text('SEP:fail\nthrow value_error("during import")\nEND_SEP:fail\nresult = fail()\n', encoding="utf-8")
        (directory / "cycle_a.sep").write_text('import "cycle_b.sep" as b\n', encoding="utf-8")
        (directory / "cycle_b.sep").write_text('import "cycle_a.sep" as a\n', encoding="utf-8")
        cases = (
            ('SEP:main\nprint "x"\nEND_SEP:main\nimport "math.sep" as math\n', "E702"),
            ('import "../outside.sep" as outside\n', "E704"),
            ('import "cycle_a.sep" as cycle\n', "E701"),
            ('import "math.sep" as math\nSEP:main\nprint math.private_value\nEND_SEP:main\n', "E706"),
            ('import "throwing.sep" as throwing\n', "E760"),
        )
        for index, (source, code) in enumerate(cases):
            with self.subTest(code=code):
                caller = directory / f"caller-{index}.sep"
                caller.write_text(source, encoding="utf-8")
                with self.assertRaises(SeparanError) as caught:
                    execute(source, str(caller), script_path=str(caller), project_root=directory)
                self.assertEqual(caught.exception.code, code)
                actual = subprocess.run([str(self.binary), str(caller)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(code, actual.stderr)

    def test_diamond_import_cache_and_big_integer_exports_match(self):
        directory = Path(self._temporary.name) / "import-diamond"
        directory.mkdir()
        (directory / "shared.sep").write_text(
            'print "shared loaded"\nconst magnitude = 10000000000000000000000000000000000000001\n'
            'SEP:value()\nreturn magnitude\nEND_SEP:value\n', encoding="utf-8")
        (directory / "left.sep").write_text(
            'import "shared.sep" as common\nSEP:value()\nreturn common.value()\nEND_SEP:value\n',
            encoding="utf-8")
        (directory / "right.sep").write_text(
            'import "shared.sep" as common\nSEP:value()\nreturn common.value()\nEND_SEP:value\n',
            encoding="utf-8")
        source = '''import "left.sep" as left
import "right.sep" as right
import "shared.sep" as direct
SEP:main
print left.value() + right.value() + direct.magnitude
END_SEP:main
'''
        caller = directory / "caller.sep"
        caller.write_text(source, encoding="utf-8")
        expected = execute(source, str(caller), script_path=str(caller), project_root=directory)[1]
        actual = subprocess.run([str(self.binary), str(caller)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)
        self.assertEqual(actual.stdout.splitlines().count("shared loaded"), 1)

    def test_print_error_stream(self):
        source = 'SEP:main\nprint "out"\nprint_error "err"\nEND_SEP:main\n'
        output, errors = io.StringIO(), io.StringIO()
        execute(source, output=output, error_output=errors)
        path = Path(self._temporary.name) / "print-error.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, output.getvalue())
        self.assertEqual(actual.stderr, errors.getvalue())

    def test_legacy_function_syntax_is_rejected(self):
        for index, source in enumerate((
            'function:main\nend_function:main\n',
            'end_function:main\n',
        )):
            with self.subTest(index=index):
                path = Path(self._temporary.name) / f"legacy-function-{index}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn("E100", actual.stderr)

    def test_check_uses_runtime_parser_without_executing_source(self):
        marker = Path(self._temporary.name) / "check-must-not-write.txt"
        source = (f'print "must not print"\nwritten = write_text("{marker.as_posix()}", "bad")\n'
                  'SEP:main\nprint "must not run main"\nEND_SEP:main\n')
        path = Path(self._temporary.name) / "check-no-side-effects.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), "--check", str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, "Separan native core: OK\n")
        self.assertFalse(marker.exists())

        invalid = Path(self._temporary.name) / "check-parser-error.sep"
        invalid.write_text('SEP:main\nprint (1 + )\nEND_SEP:main\n', encoding="utf-8")
        rejected = subprocess.run([str(self.binary), "--check", str(invalid)], capture_output=True,
                                  text=True, encoding="utf-8")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("E100", rejected.stderr)

    def compare_structure(self, source):
        try:
            Parser(Lexer(source, "case.sep").scan_tokens()).parse()
            python_code = None
        except SeparanError as exc:
            python_code = exc.code
        path = Path(self._temporary.name) / "case.sep"
        path.write_text(source, encoding="utf-8")
        native = subprocess.run([str(self.binary), "--check", str(path)], capture_output=True, text=True)
        match = re.search(r"SEPARAN (E\d+):", native.stderr)
        native_code = match.group(1) if match else None
        self.assertEqual(native.returncode == 0, python_code is None, native.stderr)
        self.assertEqual(native_code, python_code, native.stderr)

    def test_shared_block_boundaries(self):
        for source in (
            "SEP:main\nprint \"ok\"\nEND_SEP:main\n",
            "SEP:main\nprint \"ok\"\nEND_SEP:main\n",
            "SEP:main\nif true :ready\nprint \"ok\"\nendif:ready\nend_sep:main\n",
            "##note\nignored text\n##note\nSEP:main\nEND_SEP:main\n",
        ):
            with self.subTest(source=source):
                self.compare_structure(source)

    def test_shared_block_errors(self):
        for source in (
            "SEP:main\nif true :ready\nendif:wrong\nEND_SEP:main\n",
            "endif:missing\n",
            "SEP:main\n",
            "##note\nignored text\n##other\n",
        ):
            with self.subTest(source=source):
                self.compare_structure(source)

    def test_native_tokens_cli_matches_python_lexer(self):
        source = 'SEP:main\nprint "日本\\n" # note\nEND_SEP:main\n'
        expected = [
            {"type": token.type.name, "lexeme": token.lexeme,
             "line": token.position.line, "column": token.position.column}
            for token in Lexer(source, "case.sep").scan_tokens()
        ]
        path = Path(self._temporary.name) / "native-tokens.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), "--tokens", str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(json.loads(actual.stdout), expected)

        invalid_path = Path(self._temporary.name) / "native-tokens-invalid.sep"
        invalid_path.write_text('print "\\q"\n', encoding="utf-8")
        invalid = subprocess.run([str(self.binary), "--tokens", str(invalid_path)], capture_output=True,
                                 text=True, encoding="utf-8")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("E219", invalid.stderr)

    def test_native_structure_cli_matches_python_blocks(self):
        from separan.structural import inspect_source

        source = '''SEP:calculate(value)
    @operations:math:calculate
if value > 0 :positive
object:result
number amount = value
end_object:result
else:positive
list:empty_values
end_list:empty_values
endif:positive
try :finish
return value
finally:finish
print "closed"
endtry:finish
END_SEP:calculate
error:custom_error
end_error:custom_error
'''
        expected_snapshot = inspect_source(source, "case.sep")
        expected = [
            {"kind": block.kind, "label": block.label, "parent": block.parent_id,
             "line": block.start_line, "column": block.start_column, "tags": list(block.tags)}
            for block in expected_snapshot.blocks if block.id != "root"
        ]
        path = Path(self._temporary.name) / "native-structure.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), "--structure", str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        native_blocks = json.loads(actual.stdout)
        native_ids = {block["id"]: index for index, block in enumerate(native_blocks)}
        normalized = [
            {"kind": block["kind"], "label": block["label"],
             "parent": None if block["parent"] == "root" else native_blocks[native_ids[block["parent"]]]["label"],
             "line": block["line"], "column": block["column"], "tags": block["tags"]}
            for block in native_blocks
        ]
        python_parent_labels = []
        by_id = {block.id: block for block in expected_snapshot.blocks}
        for block in expected_snapshot.blocks:
            if block.id == "root":
                continue
            parent = by_id[block.parent_id]
            python_parent_labels.append(None if parent.id == "root" else parent.label)
        for block, parent in zip(expected, python_parent_labels):
            block["parent"] = parent
        self.assertEqual(normalized, expected)

        malformed = Path(self._temporary.name) / "native-structure-invalid.sep"
        malformed.write_text("SEP:main\nif true :open\n", encoding="utf-8")
        failed = subprocess.run([str(self.binary), "--structure", str(malformed)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("E106", failed.stderr)

    def test_native_semantic_tag_cli_matches_python_index(self):
        from separan.structural import inspect_tag_path

        source = '''SEP:send_alert
@operations:mail:send
END_SEP:send_alert
SEP:send_metric
@operations:metrics
END_SEP:send_metric
SEP:other
@monitoring
END_SEP:other
'''
        path = Path(self._temporary.name) / "semantic-tags.sep"
        path.write_text(source, encoding="utf-8")
        expected = inspect_tag_path(path, "operations")
        actual = subprocess.run([str(self.binary), "--tag", str(path), "@operations"],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        native = json.loads(actual.stdout)
        self.assertEqual(native["tag"], expected["tag"])
        self.assertEqual(
            [(item["name"], item["line"], item["tags"]) for item in native["functions"]],
            [(item["function"], item["line"], item["tags"]) for item in expected["functions"]],
        )

        missing = subprocess.run([str(self.binary), "--tag", str(path), "missing"],
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("S404", missing.stderr)

    def test_native_formatter_matches_python_indentation(self):
        from separan.lsp_analysis import format_source

        source = '''SEP:main
if true :choice
print "yes" # retained
else:choice
##note
if true :decorative
endif:decorative
##note
print "no"
endif:choice
END_SEP:main
'''
        expected = format_source(source)
        path = Path(self._temporary.name) / "native-format.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), "--format", str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)
        Parser(Lexer(actual.stdout, "formatted.sep").scan_tokens()).parse()

        source_without_final_newline = "SEP:main\nprint 1\nEND_SEP:main"
        path.write_text(source_without_final_newline, encoding="utf-8")
        without_final_newline = subprocess.run(
            [str(self.binary), "--format", str(path)], capture_output=True,
            text=True, encoding="utf-8",
        )
        self.assertEqual(without_final_newline.returncode, 0, without_final_newline.stderr)
        self.assertEqual(without_final_newline.stdout, format_source(source_without_final_newline))

        source_with_non_delimiter_comment = "SEP:main\n## note\n##foo-bar\nEND_SEP:main\n"
        path.write_text(source_with_non_delimiter_comment, encoding="utf-8")
        non_delimiter_comment = subprocess.run(
            [str(self.binary), "--format", str(path)], capture_output=True,
            text=True, encoding="utf-8",
        )
        self.assertEqual(non_delimiter_comment.returncode, 0, non_delimiter_comment.stderr)
        self.assertEqual(non_delimiter_comment.stdout, format_source(source_with_non_delimiter_comment))

        invalid_path = Path(self._temporary.name) / "native-format-invalid.sep"
        invalid_path.write_text('SEP:main\nprint (1 + )\nEND_SEP:main\n', encoding="utf-8")
        invalid = subprocess.run([str(self.binary), "--format", str(invalid_path)], capture_output=True,
                                 text=True, encoding="utf-8")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("E100", invalid.stderr)

    def test_native_tag_scope_verifier_matches_python_boundary_decisions(self):
        from separan.structural import inspect_file, verify_tag_scope

        before_source = '''outside = 1
SEP:target(value)
@operations:mail
result = value + 1
return result
END_SEP:target
SEP:other
return 9
END_SEP:other
'''
        cases = (
            (before_source.replace("value + 1", "value + 2"), True),
            (before_source.replace("outside = 1", "outside = 2"), False),
            (before_source.replace("@operations:mail\n", "@different:mail\n"), False),
        )
        before_path = Path(self._temporary.name) / "tag-scope-before.sep"
        before_path.write_text(before_source, encoding="utf-8")
        for index, (after_source, expected_passed) in enumerate(cases):
            after_path = Path(self._temporary.name) / f"tag-scope-after-{index}.sep"
            after_path.write_text(after_source, encoding="utf-8")
            python_report = verify_tag_scope(inspect_file(before_path), inspect_file(after_path), "operations")
            self.assertEqual(python_report["passed"], expected_passed)
            actual = subprocess.run(
                [str(self.binary), "--verify-tag-scope", str(before_path), str(after_path), "operations"],
                capture_output=True, text=True, encoding="utf-8",
            )
            report = json.loads(actual.stdout)
            self.assertEqual(report["passed"], python_report["passed"])
            self.assertEqual(actual.returncode == 0, expected_passed, actual.stderr)

    def test_ascii_token_stream(self):
        for source in (
            'SEP:main\nvalue = 0x2a + 1_000\nprint r"ok"\nEND_SEP:main\n',
            'if true && false :check\nprint "a\\n"\nendif:check\n',
            '##note\nignored text\n##note\nprint "done" # comment\n',
            'x //= 2\ny **= 3\nz = x ?? y\n',
            'empty = EMPTY\nempty_items = EMPTYS\n',
            'if true :確認\nprint "ok"\nendif:確認\n',
            '##説明\nignored text\n##説明\nprint "ok"\n',
            'SEP:main\n@通知:処理\nEND_SEP:main\n',
            'SEP:main\n@a\u0338\nEND_SEP:main\n',
        ):
            with self.subTest(source=source):
                expected = [(token.type.name, token.lexeme, token.position.line,
                             token.position.column)
                            for token in Lexer(source, "case.sep").scan_tokens()]
                result = NativeTokens()
                self.assertEqual(self.lexer.separan_lex(source.encode("utf-8"), ctypes.byref(result)), 0,
                                 result.error_code)
                try:
                    actual = [(token.type.decode(), token.lexeme.decode(), token.line, token.column)
                              for token in result.tokens[:result.count]]
                    self.assertEqual(actual, expected)
                finally:
                    self.lexer.separan_tokens_free(ctypes.byref(result))

    def test_unicode_lexer_errors_match(self):
        for source in (
            'SEP:main\nif true :cafe\u0301\nendif:cafe\u0301\nEND_SEP:main\n',
            'SEP:main\n@通知:cafe\u0301\nEND_SEP:main\n',
            'SEP:😀\n',
        ):
            with self.subTest(source=source):
                with self.assertRaises(SeparanError) as caught:
                    Lexer(source, "case.sep").scan_tokens()
                result = NativeTokens()
                self.assertNotEqual(self.lexer.separan_lex(source.encode("utf-8"), ctypes.byref(result)), 0)
                try:
                    self.assertEqual(result.error_code.decode(), caught.exception.code)
                finally:
                    self.lexer.separan_tokens_free(ctypes.byref(result))

    def test_ascii_lexer_errors(self):
        for source in ('print "unterminated\n', 'x = 1__2\n', 'print "\\q"\n',
                       '##start\n##wrong\n', 'print null\n'):
            with self.subTest(source=source):
                with self.assertRaises(SeparanError) as caught:
                    Lexer(source, "case.sep").scan_tokens()
                result = NativeTokens()
                self.assertNotEqual(self.lexer.separan_lex(source.encode(), ctypes.byref(result)), 0)
                try:
                    self.assertEqual(result.error_code.decode(), caught.exception.code)
                finally:
                    self.lexer.separan_tokens_free(ctypes.byref(result))

    def test_core_execution(self):
        for source in (
            'x = 2\nprint x\nSEP:main\nprint x + 3\nEND_SEP:main\n',
            'SEP:main\nname = "Separan"\nprint "Hello, " + name\nEND_SEP:main\n',
            'SEP:main\nn = 0\nwhile n < 3 :again\nn = n + 1\nendwhile:again\nif n == 3 :done\nprint "done"\nelse:done\nprint "wrong"\nendif:done\nEND_SEP:main\n',
            'SEP:double(n)\nreturn n * 2\nEND_SEP:double\nSEP:main\nprint double(21)\nEND_SEP:main\n',
            'SEP:main\nprint 0b1010 + 0o7 + 0xA\nEND_SEP:main\n',
            'SEP:fact(n)\nif n == 0 :base\nreturn 1\nelse:base\nreturn n * fact(n - 1)\nendif:base\nEND_SEP:fact\nSEP:main\nprint fact(5)\nEND_SEP:main\n',
            'SEP:main\nnums = [10, 20, 30]\nnums = list_append(nums, 40)\nprint first(nums)\nprint last(nums)\nprint length(nums)\nfor item in nums :each\nprint item\nendfor:each\nEND_SEP:main\n',
            'SEP:main\nscore = 75\nif score >= 80 :score_check\nprint "great"\nelseif score >= 60 :score_check\nprint "ok"\nelse:score_check\nprint "retry"\nendif:score_check\nEND_SEP:main\n',
            'SEP:main\nprint true || unknown\nprint false && unknown\nEND_SEP:main\n',
            'SEP:main\nprint upper("hello")\nprint lower("WORLD")\nprint trim("  hi  ")\nprint contains("abc", "b")\nprint starts_with("abc", "a")\nprint ends_with("abc", "c")\nprint number("42") + 1\nprint boolean("true")\nEND_SEP:main\n',
            'SEP:main\nitems = [10, 20, 10]\nprint index_of(items, 10)\nprint last_index_of(items, 10)\nprint reverse(items)\nprint slice(items, 1, 3)\nprint prepend(items, 5)\nEND_SEP:main\n',
            'SEP:main\nif true :確認\nprint "ok"\nendif:確認\nEND_SEP:main\n',
            f'SEP:main\nprint "{chr(92)}u65E5{chr(92)}U0000672C"\nprint length("{chr(92)}u65E5{chr(92)}U0000672C")\nEND_SEP:main\n',
            'SEP:main\nprint floor(3.9)\nprint ceil(3.1)\nprint sqrt(9)\nprint round(-2.5)\nEND_SEP:main\n',
            'SEP:main\nprint 1 / 2\nprint 1.0 + 2\nprint -2.0\nprint 7 // 2\nprint -7 % 3\nEND_SEP:main\n',
            'const title = "Separan"\nSEP:main\nprint title\nEND_SEP:main\n',
            'const title = "global"\nSEP:main\ntitle = "local"\nprint title\nEND_SEP:main\n',
            'object:user\nname = "Alice"\nage = 30\nobject:address\ncity = "Tokyo"\nend_object:address\nend_object:user\nSEP:main\nprint user.name\nprint user.address.city\nEND_SEP:main\n',
            'list:roles\n"admin"\n"author"\nend_list:roles\nSEP:main\nprint roles\nprint roles[1]\nEND_SEP:main\n',
            f'SEP:main\nvalue = "a{chr(92)}0b"\nprint length(value)\nprint value\nEND_SEP:main\n',
            'object:data\nz = 2\na = [1, 2, 3]\nend_object:data\nSEP:main\nprint json_encode(data)\nEND_SEP:main\n',
            'SEP:main\ndata = json_decode("{\\"z\\":2,\\"a\\":[1,2,3]}")\nprint data.a[1]\nprint json_encode(data)\nEND_SEP:main\n',
            'SEP:main\ndata = hex_decode("00FF41")\nprint data\nprint hex_encode(data)\nprint bytes_get(data, 1)\nprint slice_bytes(data, 1, 3)\nprint bytes_concat(data, bytes_from_string("B"))\nprint string_from_bytes(bytes_from_string("hi"))\nEND_SEP:main\n',
            'SEP:main\ndata = hex_decode("00FF41")\nencoded = base64_encode(data)\nprint encoded\nprint base64_decode(encoded)\nEND_SEP:main\n',
            'SEP:main\nprint pow(2, 8)\nprint min(4, 2, 9)\nprint max(4, 2, 9)\nprint average([2, 4, 6])\nprint range(1, 6, 2)\nEND_SEP:main\n',
            'SEP:main\nitems = [1, 2, 1, 3]\nprint count(items, 1)\nprint unique(items)\nprint remove_at(items, 1)\nnested = [[1, 2], [3, 4]]\nprint flatten(nested)\nEND_SEP:main\n',
            'SEP:main\nprint absolute(-5)\nprint minimum(9, 2, 4)\nprint maximum(9, 2, 4)\nprint truncate(-2.9)\nprint clamp(12, 0, 10)\nprint sign(-8)\nprint square_root(9)\nprint cube_root(8)\nprint power(2, 5)\nprint hypotenuse(3, 4)\nprint exponential(0)\nprint natural_log(1)\nprint arc_sin(0)\nprint sinh(0)\nprint to_radians(0)\nprint is_close(1, 1)\nprint is_integer_value(2.0)\nEND_SEP:main\n',
            'SEP:main\nprint greatest_common_divisor(54, 24)\nprint least_common_multiple(6, 8)\nprint factorial(6)\nprint median([3, 1, 2])\nprint median([1, 2, 3, 4])\nprint variance([1, 2, 3])\nprint sample_variance([1, 2, 3])\nprint standard_deviation([2, 2, 2])\nprint sample_standard_deviation([2, 2])\nprint percentile([0, 10, 20], 25)\nprint moving_average([1, 2, 3, 4], 2)\nprint number_to_binary(10)\nprint number_to_octal(10)\nprint number_to_hexadecimal(255)\nprint binary_to_number("1010")\nprint octal_to_number("12")\nprint hexadecimal_to_number("ff")\nprint number_to_base(35, 36)\nprint base_to_number("z", 36)\nEND_SEP:main\n',
            'object:user\nname = "Alice"\nage = 30\nend_object:user\nSEP:main\nprint object_get(user, "name")\nprint object_has(user, "age")\nprint object_has(user, "missing")\nupdated = object_set(user, "age", 31)\nprint updated.age\nprint user.age\nprint object_keys(user)\nprint object_values(user)\ntrimmed = object_remove(user, "age")\nprint object_has(trimmed, "age")\nEND_SEP:main\n',
            'SEP:main\nitems = [3, 1, 2, 1]\nprint list_remove(items, 1)\nprint remove(items, 2)\nprint sort(items)\nprint sort_descending(items)\nwords = ["beta", "Alpha", "alpha"]\nprint sort_ignore_case(words)\nprint sort_ignore_case_descending(words)\nEND_SEP:main\n',
            'object:first\nname = "ten"\nrank = 10\nend_object:first\nobject:second\nname = "two"\nrank = 2\nend_object:second\nSEP:main\nfiles = ["file10", "file2", "file1"]\nprint sort_natural(files)\nprint sort_natural_descending(files)\nmixed = ["A10", "a2", "A1"]\nprint sort_natural_ignore_case(mixed)\nprint sort_natural_ignore_case_descending(mixed)\nrows = [first, second]\nascending = sort_by(rows, "rank")\ndescending = sort_by_descending(rows, "rank")\nprint ascending[0].name\nprint descending[0].name\nEND_SEP:main\n',
            'SEP:double_item(value)\nreturn value * 2\nEND_SEP:double_item\nSEP:is_even(value)\nreturn value % 2 == 0\nEND_SEP:is_even\nSEP:add_item(total, value)\nreturn total + value\nEND_SEP:add_item\nSEP:main\nitems = [1, 2, 3, 4]\nprint map(items, double_item)\nprint filter(items, is_even)\nprint reduce(items, add_item, 0)\nEND_SEP:main\n',
            'SEP:main\nparts = split("a::b::", "::")\nprint parts\nprint join(parts, "-")\nprint replace("one two one", "one", "1")\nprint char_at("A日本", 2)\nprint compare("abc", "abd")\nprint compare_ignore_case("Alpha", "alpha")\nprint count_occurrences("aaaa", "aa")\nprint repeat("ab", 3)\nprint pad_left("7", 3, "0")\nprint pad_right("x", 3)\nEND_SEP:main\n',
            'SEP:main\nprint clip_utf8("A日本", 4)\nprint substring("A日本語", 1, 3)\nprint substring("A日本語", 2)\nprint find_all("日本-日本-日本", "日本")\nprint substring_before("key=value=more", "=")\nprint substring_after("key=value=more", "=")\nEND_SEP:main\n',
            'object:item\nvalue = 1\nend_object:item\nSEP:main\nprint reverse("A日本")\nprint index_of("日本語日本", "本")\nprint last_index_of("日本語日本", "本")\nprint exp(0)\nprint log(1)\nprint log2(8)\nprint log10(100)\nprint is_number(1)\nprint is_boolean(true)\nprint is_string("x")\nprint is_list([1])\nprint is_object(item)\nprint is_bytes(hex_decode("00"))\nprint is_datetime(1)\nprint is_duration(1)\nprint is_secret(1)\nEND_SEP:main\n',
            'SEP:main\nprint format("{} + {} = {}", 2, 3, 5)\nprint format("{{{}}}", "value")\nprint format("items: {}", [1, 2])\nEND_SEP:main\n',
            'SEP:main\nrandom_seed(12345)\nprint random_number()\nprint random_int(10, 20)\nprint random_float(1, 2)\nprint random_bool()\nprint random_pick([10, 20, 30])\nprint random_shuffle([1, 2, 3, 4])\nprint random_sample([1, 2, 3, 4], 2)\nEND_SEP:main\n',
            'SEP:main\nprint constant_time_equal("secret", "secret")\nprint constant_time_equal("secret", "other")\nprint constant_time_equal(hex_decode("00FF"), hex_decode("00FF"))\nEND_SEP:main\n',
            'SEP:main\nprint length(secure_random_bytes(16))\nvalue = secure_random_int(10, 20)\nprint value >= 10 && value <= 20\nnumber_value = secure_random_number(-5, 5)\nprint number_value >= -5 && number_value <= 5\nprint length(secure_random_string(24))\nEND_SEP:main\n',
            'SEP:main\nprint number_range(4)\nprint number_range(5, 0, -2)\nprint type_of(1)\nprint type_of("x")\nEND_SEP:main\n',
            'SEP:main\nvalue = 9007199254740993\nprint value\nprint value + 2\nprint value - 2\nprint value * 3\nprint value > 9007199254740992\nprint value == 9007199254740993\nprint value // 2\nprint value % 2\nprint json_encode(value)\nprint json_decode("9007199254740993")\nEND_SEP:main\n',
            'SEP:main\nvalue = 10000000000000000000\nprint value\nprint value + 9223372036854775807\nprint value - 10000000000000000001\nprint value * 3\nprint value // 3\nprint value % 3\nprint -value // 3\nprint -value % 3\nprint value // -3\nprint value % -3\nprint 2 ** 100\nprint value > 9999999999999999999\nprint value == 10000000000000000000.0\nprint 9999999999999999999 == 10000000000000000000.0\nprint number("10000000000000000000")\nprint string(value)\nprint json_encode(json_decode("10000000000000000000"))\nprint 0xFFFFFFFFFFFFFFFFFFFFFFFF\nEND_SEP:main\n',
            'SEP:main\nvalue = 10000000000000000000\nprint absolute(-value)\nprint sign(-value)\nprint minimum(value, 9999999999999999999)\nprint maximum(value, 9999999999999999999)\nprint clamp(value, 0, 9999999999999999999)\nprint power(2, 100)\nprint greatest_common_divisor(value, 2500000000000000000)\nprint least_common_multiple(value, 3)\nprint factorial(100)\nprint sum([value, value, -1])\nprint number_to_hexadecimal(0xFFFFFFFFFFFFFFFFFFFFFFFF)\nprint hexadecimal_to_number("ffffffffffffffffffffffff")\nprint number_to_base(value, 36)\nprint base_to_number(number_to_base(value, 36), 36)\nEND_SEP:main\n',
            'SEP:main\nprint hex_encode(sha256_hash("abc"))\nprint hex_encode(sha256_hmac("key", "The quick brown fox jumps over the lazy dog"))\nprint hex_encode(hmac_sha256("key", "The quick brown fox jumps over the lazy dog"))\nEND_SEP:main\n',
            'SEP:main\nprint hex_encode(sha512_hash("abc"))\nprint hex_encode(sha3_256_hash("abc"))\nprint hex_encode(sha3_512_hash("abc"))\nprint hex_encode(sha512_hmac("key", "The quick brown fox jumps over the lazy dog"))\nEND_SEP:main\n',
            'SEP:main\nnow = unix_time()\nprint now > 1700000000\nprint now < 4102444800\nEND_SEP:main\n',
            'SEP:main\nprint xml_escape_text("<tag>&")\nprint xml_escape_attribute("<tag a=\\"x\\">\'&")\nprint xml_unescape("&lt;ok&gt; &amp; &#x65E5;&#26412;")\nEND_SEP:main\n',
            'SEP:main\nvalue = duration("1d2h3m4s5ms")\nprint value\nprint duration_milliseconds(value)\nprint type(value)\nprint is_duration(value)\nprint value + duration("1s")\nprint value - duration("5ms")\nprint duration("2s") * 3\nprint duration("6s") / 3\nprint duration("6s") / duration("2s")\nprint duration("1s") < duration("2s")\nprint sort([duration("3s"), duration("1s"), duration("2s")])\nEND_SEP:main\n',
            'SEP:main\nprint timezone("UTC")\nprint timezone("+09:00")\nlocal = local_datetime("2024-02-29T12:34:56.1")\nprint local\nprint type(local)\nprint sort([local_datetime("2024-01-02T00:00:00"), local_datetime("2024-01-01T00:00:00")])\nEND_SEP:main\n',
            'SEP:main\nvalue = datetime_parse("2024-02-29T12:34:56.123+09:00")\nprint value\nprint type(value)\nprint is_datetime(value)\nprint datetime_year(value)\nprint datetime_month(value)\nprint datetime_day(value)\nprint datetime_hour(value)\nprint datetime_minute(value)\nprint datetime_second(value)\nprint datetime_millisecond(value)\nprint datetime_weekday(value)\nprint datetime_offset(value)\nprint datetime_timezone(value)\nprint unix_milliseconds_from_datetime(value)\nprint datetime_from_unix_milliseconds(unix_milliseconds_from_datetime(value), timezone("+09:00"))\nprint datetime_in_timezone(value, timezone("UTC"))\nlocal = local_datetime("2024-02-29T12:34:56.123")\nprint datetime_from_local(local, timezone("+09:00"))\nprint value + duration("1s")\nprint value - duration("123ms")\nprint value - datetime_parse("2024-02-29T03:34:56.123Z")\nEND_SEP:main\n',
            'SEP:main\nvalue = datetime_parse("2024-02-29T12:34:56.123+09:00")\nprint datetime_valid(2024, 2, 29)\nprint datetime_valid(2023, 2, 29)\nprint datetime_format(value, "yyyy/MM/dd HH:mm:ss.SSS XXX")\nprint unix_seconds_from_datetime(value)\nprint unix_time(value)\nnow = datetime_now("UTC")\nprint datetime_year(now) > 2020\nEND_SEP:main\n',
            'SEP:main\nvalue = datetime(2024, 2, 29, 12, 34, 56, timezone = "+09:00")\nprint value\nprint datetime_timezone(value)\nEND_SEP:main\n',
            'SEP:main\nvalues = [1, 2]\nlist_insert(values, 1, 2)\nprint values\nprint type_of(value_error("bad"))\nprint value_error("bad")\nprint value_error("bad") == value_error("bad")\nEND_SEP:main\n',
            'SEP:main\nvalues = [[1, 2, 3], [4, 5, 6]]\nlist_remove_horizontal(values, 0, 1, 1)\nprint values\nEND_SEP:main\n',
            'SEP:main\nvalues = [[1, 2], [3, 4], [5, 6]]\nlist_remove_vertical(values, 1, 0, 1)\nprint values\nEND_SEP:main\n',
            'SEP:main\ntry :work\nthrow value_error("bad")\ncatch type_error :work\nprint "wrong"\ncatch value_error :work\nprint "caught"\nfinally:work\nprint "finally"\nendtry:work\nEND_SEP:main\n',
            'SEP:main\ntry :crypto\nthrow crypto_authentication_error("bad tag")\ncatch crypto_error :crypto\nprint "crypto"\nendtry:crypto\nEND_SEP:main\n',
            'SEP:answer\ntry :returning\nreturn 42\nfinally:returning\nprint "cleanup"\nendtry:returning\nEND_SEP:answer\nSEP:main\nprint answer()\nEND_SEP:main\n',
            'error:payment_error\nend_error:payment_error\nSEP:main\ntry :pay\nthrow payment_error("declined")\ncatch payment_error :pay\nprint "custom"\nendtry:pay\nEND_SEP:main\n',
            'SEP:main\ntry :divide\nprint 1 / 0\ncatch value_error :divide\nprint "zero"\nendtry:divide\ntry :file\nprint read_text("__missing_runtime_file__.txt")\ncatch io_error :file\nprint "missing"\nendtry:file\nEND_SEP:main\n',
            'SEP:main\nvalues = [[1, 2], [3, 4]]\nvalues[0][1] = 7\nvalues[1][0] = 8\nprint values\nEND_SEP:main\n',
            'SEP:main\nnumber count = 1\nstring name = "Separan"\nboolean active = true\nlist<number> values = []\nvalues = [1, 2]\nlist<list<number>> matrix = [[1, 2], [3]]\ncount = 2\nprint count\nprint name\nprint active\nprint values\nprint matrix\nEND_SEP:main\n',
            'SEP:main\nnumber age = EMPTY\nprint age is EMPTY\nprint type_of(age)\nage = 30\nprint age is not EMPTY\nlist<number> values = [1, 2]\nvalues[1] = EMPTY\nprint values[1] is EMPTY\nprint type_of(values[1])\nvalues[1] = 4\nprint values\nEND_SEP:main\n',
            'SEP:main\nlist<number> empty_values = EMPTYS\nprint empty_values is EMPTYS\nvalues = [1, 2, 3]\nvalues = EMPTYS\nprint values is EMPTYS\nprint length(values)\nprint values\nEND_SEP:main\n',
            'SEP:typed(value: number, labels: list<string>)\nprint value\nprint labels\nEND_SEP:typed\nSEP:main\ntyped(7, ["a", "b"])\nEND_SEP:main\n',
            'object:user\nstring name = "Alice"\nnumber age = 30\nlist<number> scores = [10, 20]\nend_object:user\nprint user.name\nuser = EMPTYS\nprint user is EMPTYS\nprint user.name is EMPTY\nprint type_of(user.name)\nprint length(user.scores)\n',
            'SEP:main\nage = 1\nage = EMPTY\nprint age is EMPTY\nprint type_of(age)\nage = 2\nprint age\nEND_SEP:main\n',
            'SEP:main\nvalues = [1, EMPTY]\nprint values\nprint type_of(values[1])\nlist<list<number>> nested = [[EMPTY, EMPTY], [EMPTY]]\nnested[0][1] = 7\nprint nested\nEND_SEP:main\n',
            'SEP:main\nlist<list<number>> values = [[1, 2], [3, 4, 5], [6]]\nvalues[1][1] = EMPTY\nprint values\nvalues[1] = EMPTYS\nprint values\nvalues = EMPTYS\nprint values\nEND_SEP:main\n',
            'object:data\nstring name = EMPTY\nlist<number> values = [1, 2]\nend_object:data\nSEP:main\nupdated = object_set(data, "name", "Alice")\nprint updated.name\ncleared = object_set(updated, "name", EMPTY)\nprint cleared.name is EMPTY\nprint type_of(cleared.name)\nempty_values = object_set(data, "values", EMPTYS)\nprint empty_values.values\nEND_SEP:main\n',
            'SEP:main\nstring optional = json_decode("null")\nprint optional is EMPTY\nprint type_of(optional)\nprint json_encode(optional)\nmixed = json_decode("[1,null]")\nprint type_of(mixed[1])\nprint json_encode(mixed)\nunknown = json_decode("[null,null]")\nunknown[1] = 7\nprint type_of(unknown[0])\nprint json_encode(unknown)\ndata = json_decode("{\\"value\\":null}")\nupdated = object_set(data, "value", 42)\nprint updated.value\nEND_SEP:main\n',
            'SEP:check(value)\nreturn value is EMPTY\nEND_SEP:check\nSEP:typed(value: number)\nreturn value is EMPTY\nEND_SEP:typed\nSEP:main\nnumber source = EMPTY\nprint check(source)\nprint typed(EMPTY)\nEND_SEP:main\n',
            'SEP:fail\nprint "called"\nreturn 9\nEND_SEP:fail\nSEP:main\nprint 1 ?? fail()\nnumber first = EMPTY\nnumber second = EMPTY\nprint first ?? second ?? 3\nprint false ?? true\nvalue = 2\nvalue **= 3\nvalue += 1\nvalue *= 2\nvalue //= 3\nvalue %= 5\nvalue -= 1\nvalue /= 2\nprint value\nitems = [1]\nitems += [2, 3]\nprint items\nEND_SEP:main\n',
            'object:user\nname = "Alice"\nend_object:user\nSEP:main\nprint "bc" in "abcd"\nprint "z" not in "abcd"\nprint 2 in [1, 2, 3]\nprint "name" in user\ndata = hex_decode("00FF10")\nprint 255 in data\nprint hex_decode("FF10") in data\nEND_SEP:main\n',
            'SEP:main\nlist<number> values = [1, 2, 3, 4]\nlist_insert(values, front, 1)\nlist_insert(values, back, 1)\nprint values\nlist_remove(values, front, 1)\nlist_remove(values, 1, 2)\nlist_remove(values, back, 1)\nprint values\nlist<number> empty_values = []\nlist_insert(empty_values, back, 2)\nprint type_of(empty_values[0])\nEND_SEP:main\n',
        ):
            with self.subTest(source=source):
                expected = execute(source)[1]
                path = Path(self._temporary.name) / "run.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)],
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(actual.returncode, 0, actual.stderr)
                self.assertEqual(actual.stdout, expected)

    def test_index_assignment_errors_match(self):
        cases = (
            'SEP:main\nvalues = [1]\nvalues[1] = 2\nEND_SEP:main\n',
            'SEP:main\nvalues = [1]\nvalues[0] = "x"\nEND_SEP:main\n',
            'SEP:main\nconst values = [1]\nvalues[0] = 2\nEND_SEP:main\n',
        )
        for index, source in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                path = Path(self._temporary.name) / f"index-error-{index}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(caught.exception.code, actual.stderr)

    def test_big_integer_range_random_and_statistics_match(self):
        source = '''SEP:main
big = 1000000000000000000000000000000
print range(big, big + 3)
print range(big + 2, big - 1, -1)
print random_int(big, big)
print secure_random_int(big, big)
random_seed(9)
value = random_int(big, big + 3)
print value >= big && value <= big + 3
value = secure_random_int(big, big + 3)
print value >= big && value <= big + 3
wide = 100000000000000000000000000000000000000000000000000
random_seed(11)
value = random_int(wide, wide * 2)
print value >= wide && value <= wide * 2
value = secure_random_int(wide, wide * 2)
print value >= wide && value <= wide * 2
print average([big, big])
print median([big - 1, big + 1])
print percentile([big - 1, big + 1], 50)
END_SEP:main
'''
        expected = execute(source)[1]
        path = Path(self._temporary.name) / "bigint-boundaries.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_big_integer_fixed_width_boundaries_match(self):
        cases = (
            'print datetime_from_unix_milliseconds(1000000000000000000000000000000, timezone("UTC"))\n',
            'print duration("1s") * 1000000000000000000000000000000\n',
            'values = [1]\nprint values[1000000000000000000000000000000]\n',
            'print random_int(100000000000000000000, 99999999999999999999)\n',
            'print secure_random_int(100000000000000000000, 99999999999999999999)\n',
        )
        for index, source in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                path = Path(self._temporary.name) / f"bigint-fixed-width-{index}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(caught.exception.code, actual.stderr)

    def test_floating_point_boundaries_match(self):
        source = '''print -0.0
print 0.0 == -0.0
print round(2.675, 2)
print round(-2.675, 2)
    print round(1.2345678901234567, 16)
    print round(-1.2345678901234567, 16)
print round(1.0000000000000002, 16)
print round(999999999999999.9, 1)
print round(1234567890123456.7, -1)
print is_close(9007199254740992, 9007199254740993)
print 9007199254740992 == 9007199254740992.0
print 9007199254740993 == 9007199254740992.0
print square_root(2)
'''
        expected = execute(source)[1]
        path = Path(self._temporary.name) / "floating-boundaries.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

        for invalid in ('print 1.0 / -0.0\n', 'print natural_log(0)\n'):
            with self.subTest(source=invalid):
                with self.assertRaises(SeparanError) as caught:
                    execute(invalid)
                path.write_text(invalid, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(caught.exception.code, actual.stderr)

    def test_extended_math_outputs_and_domain_errors_match(self):
        source = '''SEP:main
print exponential_base2(3)
print log_base2(8)
print log_base10(1000)
print is_close(log_one_plus(0.0000000000000001), 0.0000000000000001)
print is_close(arc_sin(1), to_radians(90))
print is_close(arc_cos(-1), to_radians(180))
print is_close(arc_tan(1), to_radians(45))
print is_close(arc_tan2(1, 1), to_radians(45))
print is_close(arc_sinh(sinh(0.5)), 0.5)
print is_close(arc_cosh(cosh(0.5)), 0.5)
print is_close(arc_tanh(tanh(0.5)), 0.5)
print is_close(to_degrees(to_radians(360)), 360)
print is_finite(1)
print is_infinite(0)
print is_nan(0)
print is_integer_value(1.0)
print is_integer_value(1.25)
END_SEP:main
'''
        expected = execute(source)[1]
        path = Path(self._temporary.name) / "extended-math.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

        for index, expression in enumerate((
            "exponential(1000)", "exponential_base2(1024)", "sinh(1000)",
            "cosh(1000)", "log_one_plus(-1)", "arc_cosh(0.5)",
            "arc_tanh(1)", "arc_sin(1.0000000000000002)",
        )):
            invalid_source = f"SEP:main\nprint {expression}\nEND_SEP:main\n"
            invalid_path = Path(self._temporary.name) / f"extended-math-error-{index}.sep"
            invalid_path.write_text(invalid_source, encoding="utf-8")
            with self.subTest(expression=expression):
                with self.assertRaises(SeparanError) as caught:
                    execute(invalid_source)
                self.assertEqual(caught.exception.code, "E308")
                failed = subprocess.run([str(self.binary), str(invalid_path)],
                                        capture_output=True, text=True, encoding="utf-8")
                match = re.search(r"SEPARAN (E\d+):", failed.stderr)
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(match.group(1) if match else None, "E308", failed.stderr)

    def test_bytes_encoding_values_and_errors_match(self):
        source = '''SEP:main
print hex_encode(bytes_from_string("A", encoding = "ascii"))
print hex_encode(bytes_from_string("日", encoding = "utf-16le"))
print hex_encode(bytes_from_string("A", encoding = "utf-16be"))
print string_from_bytes(hex_decode("4142"), encoding = "ascii")
print string_from_bytes(hex_decode("4100"), encoding = "utf-16le")
print string_from_bytes(hex_decode("0041"), encoding = "utf-16be")
print string_from_bytes(bytes_from_string("日本", encoding = "utf-16le"), encoding = "utf-16le")
print string_from_bytes(bytes_from_string("A😀日本", encoding = "utf-16be"), encoding = "utf-16be")
print string_from_bytes(hex_decode(""), encoding = "utf-16le")
END_SEP:main
'''
        expected = execute(source)[1]
        path = Path(self._temporary.name) / "bytes-encoding.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

        cases = (
            ('bytes_from_string("日", encoding = "ascii")', "E621"),
            ('string_from_bytes(hex_decode("FF"), encoding = "ascii")', "E621"),
            ('string_from_bytes(hex_decode("00"), encoding = "utf-16le")', "E621"),
            ('string_from_bytes(hex_decode("00D8"), encoding = "utf-16le")', "E621"),
            ('string_from_bytes(hex_decode("00DC"), encoding = "utf-16le")', "E621"),
            ('string_from_bytes(hex_decode("00D84100"), encoding = "utf-16le")', "E621"),
            ('bytes_from_string("A", encoding = "latin1")', "E620"),
            ('bytes_from_string("A", encoding = 1)', "E201"),
        )
        for index, (expression, expected_code) in enumerate(cases):
            invalid_source = f"SEP:main\nprint {expression}\nEND_SEP:main\n"
            invalid_path = Path(self._temporary.name) / f"bytes-encoding-error-{index}.sep"
            invalid_path.write_text(invalid_source, encoding="utf-8")
            with self.subTest(expression=expression):
                with self.assertRaises(SeparanError) as caught:
                    execute(invalid_source)
                self.assertEqual(caught.exception.code, expected_code)
                failed = subprocess.run([str(self.binary), str(invalid_path)],
                                        capture_output=True, text=True, encoding="utf-8")
                match = re.search(r"SEPARAN (E\d+):", failed.stderr)
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(match.group(1) if match else None, expected_code, failed.stderr)

    def test_extreme_exact_power_is_limited(self):
        source = 'print 2 ** 1000000000\n'
        path = Path(self._temporary.name) / "exact-power-limit.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8", timeout=3)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn("E308", actual.stderr)

    def test_all_builtin_empty_value_contracts_match(self):
        checked = 0
        for name, builtin in BUILTINS.items():
            if builtin.minimum_arguments == 0:
                continue
            arguments = ", ".join(["EMPTY"] * builtin.minimum_arguments)
            source = f"SEP:main\nprint {name}({arguments})\nEND_SEP:main\n"
            try:
                execute(source)
            except SeparanError as caught:
                if caught.code != "E131":
                    continue
            else:
                continue
            checked += 1
            path = Path(self._temporary.name) / f"empty-{name}.sep"
            path.write_text(source, encoding="utf-8")
            actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                    text=True, encoding="utf-8")
            with self.subTest(name=name):
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn("E131", actual.stderr)
        self.assertGreater(checked, 300)

    def test_typed_declaration_errors_match(self):
        cases = (
            'SEP:main\nnumber count = "1"\nEND_SEP:main\n',
            'SEP:main\nnumber value = 1\nnumber value = 2\nEND_SEP:main\n',
            'SEP:main\nconst string name = "a"\nname = "b"\nEND_SEP:main\n',
            'SEP:main\nlist<number> values = ["x"]\nEND_SEP:main\n',
            'SEP:typed(value: number)\nprint value\nEND_SEP:typed\nSEP:main\ntyped("x")\nEND_SEP:main\n',
            'SEP:main\nvalue = EMPTY\nEND_SEP:main\n',
            'SEP:main\nconst number value = EMPTY\nEND_SEP:main\n',
            'SEP:main\nnumber value = EMPTY\nprint value\nEND_SEP:main\n',
            'SEP:main\nnumber value = EMPTY\nprint value + 1\nEND_SEP:main\n',
            'SEP:main\nboolean value = EMPTY\nif value :present\nendif:present\nEND_SEP:main\n',
            'SEP:main\nstring value = EMPTY\nprint upper(value)\nEND_SEP:main\n',
            'SEP:main\nvalues = [EMPTY, EMPTY]\nEND_SEP:main\n',
            'SEP:main\nlist<number> values = [1, EMPTY]\nsorted = sort(values)\nEND_SEP:main\n',
            'object:user\nstring name = EMPTY\nend_object:user\nSEP:main\nbad = object_set(user, "name", 1)\nEND_SEP:main\n',
            'object:user\nname = "Alice"\nend_object:user\nSEP:main\nbad = object_set(user, "new", EMPTY)\nEND_SEP:main\n',
            'SEP:check(value)\nreturn value is EMPTY\nEND_SEP:check\nSEP:main\nprint check(EMPTY)\nEND_SEP:main\n',
            'SEP:main\nvalue = front\nEND_SEP:main\n',
            'SEP:main\nprint type_of(back)\nEND_SEP:main\n',
        )
        for index, source in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                path = Path(self._temporary.name) / f"typed-error-{index}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(caught.exception.code, actual.stderr)

    def test_top_level_declaration_errors_match(self):
        cases = (
            'SEP:work\nEND_SEP:work\nSEP:work\nEND_SEP:work\n',
            'SEP:main(value)\nEND_SEP:main\n',
            'SEP:length\nEND_SEP:length\n',
            'error:value_error\nend_error:value_error\n',
            'error:custom_error\nend_error:custom_error\nerror:custom_error\nend_error:custom_error\n',
            'SEP:conflict\nEND_SEP:conflict\nerror:conflict\nend_error:conflict\n',
            'http_route GET "/user/:id/:id" :bad\nend_http_route:bad\n',
            'http_route GET "/x" :a\nend_http_route:a\nhttp_route GET "/x" :b\nend_http_route:b\n',
        )
        for index, source in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                path = Path(self._temporary.name) / f"declaration-error-{index}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(caught.exception.code, actual.stderr)

    def test_format_maximum_argument_count_matches(self):
        source = 'SEP:main\nprint format(' + ', '.join(['"x"'] * 65) + ')\nEND_SEP:main\n'
        with self.assertRaises(SeparanError) as caught:
            execute(source)
        self.assertEqual(caught.exception.code, "E207")
        path = Path(self._temporary.name) / "format-too-many.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn("E207", actual.stderr)

    def test_unknown_builtin_named_arguments_match(self):
        for index, source in enumerate((
            'SEP:main\nprint length("x", unknown = 1)\nEND_SEP:main\n',
            'SEP:main\nprint regex_find("a", "a", unknown = true)\nEND_SEP:main\n',
            'SEP:main\nprint http_get("https://example.test", unknown = 1)\nEND_SEP:main\n',
        )):
            with self.subTest(index=index):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                self.assertEqual(caught.exception.code, "E207")
                path = Path(self._temporary.name) / f"unknown-named-{index}.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8")
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn("E207", actual.stderr)

    def test_negative_language_corpus_error_codes_match(self):
        from tests.test_negative_conformance import SYNTAX_CASES, RUNTIME_CASES
        positioned_runtime_cases = {name for name, _, _ in RUNTIME_CASES}
        positioned_syntax_cases = {name for name, _, _ in SYNTAX_CASES}
        for case_name, source, code in SYNTAX_CASES + RUNTIME_CASES:
            with self.subTest(case=case_name):
                python_output = io.StringIO()
                with self.assertRaises(SeparanError) as caught:
                    execute(source, output=python_output)
                self.assertEqual(caught.exception.code, code)
                path = Path(self._temporary.name) / f"negative-{case_name}.sep"
                path.write_text(source, encoding="utf-8")
                binary = self.regex_binary if case_name == "unknown_regex_method" else self.binary
                actual = subprocess.run([str(binary), str(path)], capture_output=True,
                                        text=True, encoding="utf-8", timeout=3)
                self.assertNotEqual(actual.returncode, 0)
                match = re.search(r"SEPARAN (E\d+):", actual.stderr)
                self.assertIsNotNone(match, actual.stderr)
                self.assertEqual(match.group(1), code, actual.stderr)
                if case_name in positioned_runtime_cases or case_name in positioned_syntax_cases:
                    location = re.search(r"at line (\d+), column (\d+)", actual.stderr)
                    self.assertIsNotNone(location, actual.stderr)
                    self.assertEqual((int(location.group(1)), int(location.group(2))),
                                     (caught.exception.position.line, caught.exception.position.column), actual.stderr)
                self.assertEqual(actual.stdout, python_output.getvalue())

    def test_unicode_runtime_diagnostic_position_matches(self):
        source = 'SEP:main\nprint "日本" + 1\nEND_SEP:main\n'
        with self.assertRaises(SeparanError) as caught:
            execute(source)
        path = Path(self._temporary.name) / "unicode-runtime-position.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn(caught.exception.code, actual.stderr)
        location = re.search(r"at line (\d+), column (\d+)", actual.stderr)
        self.assertIsNotNone(location, actual.stderr)
        self.assertEqual((int(location.group(1)), int(location.group(2))),
                         (caught.exception.position.line, caught.exception.position.column), actual.stderr)

    def test_runtime_error_categories_match_python(self):
        source = '''SEP:main
try :type
print true + 1
catch type_error :type
print "type_error"
catch any :type
print "wrong type category"
endtry:type
try :value
print 1 / 0
catch value_error :value
print "value_error"
catch any :value
print "wrong value category"
endtry:value
try :index
print [1][1]
catch index_error :index
print "index_error"
catch any :index
print "wrong index category"
endtry:index
try :conversion
print number("bad")
catch runtime_error :conversion
print "runtime_error"
catch any :conversion
print "wrong conversion category"
endtry:conversion
END_SEP:main
'''
        expected = execute(source)[1]
        self.assertEqual(expected.splitlines(), ["type_error", "value_error", "index_error", "runtime_error"])
        for expression, code, category in (
            ("true + 1", "E201", "type_error"),
            ("1 / 0", "E301", "value_error"),
            ("[1][1]", "E302", "index_error"),
            ('number("bad")', "E304", "runtime_error"),
        ):
            with self.subTest(expression=expression):
                with self.assertRaises(SeparanError) as caught:
                    execute(f"print {expression}\n")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(Interpreter._error_category(caught.exception), category)
                self.assertTrue(caught.exception.description)
                self.assertGreaterEqual(caught.exception.position.line, 1)
        path = Path(self._temporary.name) / "runtime-error-categories.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_input_builtin(self):
        source = 'SEP:main\nname = input("Name: ")\nprint name\nEND_SEP:main\n'
        expected = execute(source, input_stream=io.StringIO("Alice\n"))[1]
        path = Path(self._temporary.name) / "input.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], input="Alice\n",
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_command_arguments_and_script_path(self):
        source = ('SEP:main\nprint command_args()\nprint script_path()\n'
                  'print arg_exists("--name")\nprint arg_exists("--missing")\n'
                  'print arg_value("--name")\nprint arg_value("--missing", default = "fallback")\nEND_SEP:main\n')
        path = Path(self._temporary.name) / "arguments.sep"
        path.write_text(source, encoding="utf-8")
        arguments = ["--name=Alice", "tail"]
        expected = execute(source, command_arguments=arguments, script_path=str(path))[1]
        actual = subprocess.run([str(self.binary), str(path), *arguments],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_environment_builtins(self):
        key = "SEPARAN_C_TEST_MODE_X9"
        source = (f'SEP:main\nprint env_exists("{key}")\nenv_set("{key}", "test")\n'
                  f'print env_get("{key}")\nenv_remove("{key}")\nprint env_exists("{key}")\n'
                  f'print env_get("{key}", default = "fallback")\nEND_SEP:main\n')
        expected = execute(source, environment_variables={})[1]
        path = Path(self._temporary.name) / "environment.sep"
        path.write_text(source, encoding="utf-8")
        environment = os.environ.copy()
        environment.pop(key, None)
        actual = subprocess.run([str(self.binary), str(path)], env=environment,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_core_type_error_rejected(self):
        source = 'SEP:main\nx = 1\nx = "one"\nEND_SEP:main\n'
        with self.assertRaises(SeparanError):
            execute(source)
        path = Path(self._temporary.name) / "type_error.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn("variable type cannot change", actual.stderr)

    def test_constant_reassignment_rejected(self):
        source = 'const name = "first"\nname = "second"\n'
        with self.assertRaises(SeparanError):
            execute(source)
        path = Path(self._temporary.name) / "const_error.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn("constant cannot be reassigned", actual.stderr)

    def test_core_error_codes(self):
        for source in (
            'print missing\n',
            'print missing()\n',
            'SEP:f(x)\nreturn x\nEND_SEP:f\nprint f()\n',
            'x = [1, "two"]\n',
            'x = 1\nx = "one"\n',
            'const x = 1\nx = 2\n',
            'print json_decode("{\\"a\\":1,\\"a\\":2}")\n',
            'unknown()\n',
            'print hex_decode("F")\n',
            'print base64_decode("###=")\n',
            'print string_from_bytes(hex_decode("FF"))\n',
        ):
            with self.subTest(source=source):
                with self.assertRaises(SeparanError) as caught:
                    execute(source)
                path = Path(self._temporary.name) / "error.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
                self.assertNotEqual(actual.returncode, 0)
                self.assertIn(caught.exception.code, actual.stderr)

    def test_file_read_capability(self):
        directory = Path(self._temporary.name)
        (directory / "data.txt").write_text("hello\n", encoding="utf-8")
        source = ('SEP:main\nprint file_exists("data.txt")\n'
                  'print file_exists("missing.txt")\nprint file_size("data.txt")\n'
                  'print read_text("data.txt")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "files.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_glob_capability(self):
        directory = Path(self._temporary.name)
        (directory / "nested").mkdir(exist_ok=True)
        (directory / "alpha.txt").write_text("a", encoding="utf-8")
        (directory / "nested" / "beta.txt").write_text("b", encoding="utf-8")
        (directory / "nested" / "skip.bin").write_bytes(b"x")
        source = 'SEP:main\nprint glob("*.txt")\nprint glob("**/*.txt")\nEND_SEP:main\n'
        expected = execute(source, project_root=directory)[1]
        path = directory / "glob.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_file_path_escape_rejected(self):
        directory = Path(self._temporary.name)
        source = 'print read_text("../outside.txt")\n'
        with self.assertRaises(SeparanError) as caught:
            execute(source, project_root=directory)
        path = directory / "escape.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn(caught.exception.code, actual.stderr)

    def test_invalid_utf8_file_rejected(self):
        directory = Path(self._temporary.name)
        (directory / "invalid.txt").write_bytes(b"\xff")
        source = 'print read_text("invalid.txt")\n'
        with self.assertRaises(SeparanError) as caught:
            execute(source, project_root=directory)
        path = directory / "invalid_file.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn(caught.exception.code, actual.stderr)

    def test_file_write_capability(self):
        directory = Path(self._temporary.name)
        source = ('SEP:main\nwrite_text("nested/note.txt", "hello")\n'
                  'append_text("nested/note.txt", " world")\n'
                  'print read_text("nested/note.txt")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "write.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)
        self.assertEqual((directory / "nested" / "note.txt").read_text(encoding="utf-8"), "hello world")

    def test_directory_and_file_lifecycle(self):
        directory = Path(self._temporary.name)
        source = ('SEP:main\nprint directory_exists("fresh")\n'
                  'create_directory("fresh")\nprint directory_exists("fresh")\n'
                  'write_text("fresh/note.txt", "x")\nprint file_exists("fresh/note.txt")\n'
                  'delete_file("fresh/note.txt")\ndelete_directory("fresh")\n'
                  'print directory_exists("fresh")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "lifecycle.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)
        self.assertFalse((directory / "fresh").exists())

    def test_lines_and_directory_listing(self):
        directory = Path(self._temporary.name)
        listing = directory / "listing"
        listing.mkdir()
        (listing / "b.txt").write_text("one\ntwo\n", encoding="utf-8")
        (listing / "a.txt").write_text("a", encoding="utf-8")
        source = ('SEP:main\nprint list_directory("listing")\n'
                  'print read_lines("listing/b.txt")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "listing.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_file_path_helpers(self):
        directory = Path(self._temporary.name)
        (directory / "paths").mkdir()
        (directory / "paths" / "note.txt").write_text("x", encoding="utf-8")
        source = ('SEP:main\nprint file_name("paths/note.txt")\n'
                  'print file_extension("paths/note.txt")\n'
                  'print parent_directory("paths/note.txt")\n'
                  'print absolute_path("paths/note.txt")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "path_helpers.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)

    def test_copy_and_move_file(self):
        directory = Path(self._temporary.name)
        (directory / "source.txt").write_text("content", encoding="utf-8")
        source = ('SEP:main\ncopy_file("source.txt", "copy.txt")\n'
                  'move_file("copy.txt", "moved.txt")\n'
                  'print read_text("moved.txt")\n'
                  'delete_file("moved.txt")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "copy_move.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)
        self.assertFalse((directory / "copy.txt").exists())
        self.assertFalse((directory / "moved.txt").exists())

    def test_copy_refuses_existing_destination(self):
        directory = Path(self._temporary.name)
        (directory / "source.txt").write_text("source", encoding="utf-8")
        (directory / "destination.txt").write_text("destination", encoding="utf-8")
        source = 'SEP:main\ncopy_file("source.txt", "destination.txt")\nEND_SEP:main\n'
        with self.assertRaises(SeparanError) as caught:
            execute(source, project_root=directory)
        path = directory / "copy_conflict.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True, text=True)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIn(caught.exception.code, actual.stderr)
        self.assertEqual((directory / "destination.txt").read_text(encoding="utf-8"), "destination")

    def test_binary_file_round_trip(self):
        directory = Path(self._temporary.name)
        (directory / "blob.bin").write_bytes(b"\x00\xffx")
        source = ('SEP:main\nwrite_bytes("copy.bin", read_bytes("blob.bin"))\n'
                  'print read_bytes("copy.bin")\nprint file_size("copy.bin")\n'
                  'delete_file("copy.bin")\nEND_SEP:main\n')
        expected = execute(source, project_root=directory)[1]
        path = directory / "bytes.sep"
        path.write_text(source, encoding="utf-8")
        actual = subprocess.run([str(self.binary), str(path)], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected)
        self.assertFalse((directory / "copy.bin").exists())


if __name__ == "__main__":
    unittest.main()
