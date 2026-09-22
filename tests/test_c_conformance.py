"""Cross implementation checks for the native structural validator.

The native CLI currently validates structure; execution parity is a later gate.
Keep these cases small so a mismatch points to one language rule.
"""

import re
import ctypes
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
            [compiler, "-std=c11", "-Wall", "-Wextra", "-I", str(c_root / "include"),
             str(c_root / "src" / "main.c"), str(c_root / "src" / "separan_core.c"),
             str(c_root / "src" / "separan_lexer.c"), str(c_root / "src" / "separan_files.c"),
             str(c_root / "src" / "separan_runtime.c"),
             "-o", str(cls.binary), "-lm"],
            check=True, capture_output=True, text=True,
        )
        library = Path(cls._temporary.name) / ("lexer.dll" if sys.platform == "win32" else "lexer.so")
        subprocess.run(
            [compiler, "-std=c11", "-Wall", "-Wextra", "-shared", "-fPIC",
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
            "SEP:main\nprint \"ok\"\nend_SEP:main\n",
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

    def test_ascii_token_stream(self):
        for source in (
            'SEP:main\nvalue = 0x2a + 1_000\nprint r"ok"\nEND_SEP:main\n',
            'if true && false :check\nprint "a\\n"\nendif:check\n',
            '##note\nignored text\n##note\nprint "done" # comment\n',
            'x //= 2\ny **= 3\nz = x ?? y\n',
            'empty = EMPTY\nempty_items = EMPTYS\n',
            'if true :確認\nprint "ok"\nendif:確認\n',
            '##説明\nignored text\n##説明\nprint "ok"\n',
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
        ):
            with self.subTest(source=source):
                expected = execute(source)[1]
                path = Path(self._temporary.name) / "run.sep"
                path.write_text(source, encoding="utf-8")
                actual = subprocess.run([str(self.binary), str(path)],
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
