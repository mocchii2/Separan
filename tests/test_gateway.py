import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C_ROOT = ROOT / "reference" / "c"


def fcgi_record(record_type, request_id, content=b""):
    header = struct.pack(">BBHHBB", 1, record_type, request_id, len(content), 0, 0)
    return header + content


def fcgi_length(length):
    if length < 128:
        return bytes([length])
    return struct.pack(">I", length | 0x80000000)


def fcgi_params(values):
    encoded = bytearray()
    for name, value in values.items():
        name_bytes, value_bytes = name.encode(), value.encode()
        encoded += fcgi_length(len(name_bytes)) + fcgi_length(len(value_bytes))
        encoded += name_bytes + value_bytes
    return bytes(encoded)


def parse_fcgi_records(data):
    records = []
    offset = 0
    while offset < len(data):
        version, record_type, request_id, content_length, padding_length, _ = struct.unpack_from(">BBHHBB", data, offset)
        offset += 8
        content = data[offset:offset + content_length]
        offset += content_length + padding_length
        if version != 1:
            raise AssertionError(f"unexpected FastCGI version {version}")
        records.append((record_type, request_id, content))
    return records


class GatewayWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            raise unittest.SkipTest("a C compiler is required for gateway tests")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary.name) / ("separan-gw.exe" if __import__("os").name == "nt" else "separan-gw")
        sources = [
            C_ROOT / "src" / "separan_gw.c",
            C_ROOT / "src" / "separan_gw_fastcgi.c",
            C_ROOT / "src" / "separan_gw_supervisor.c",
            C_ROOT / "src" / "separan_core.c",
            C_ROOT / "src" / "separan_lexer.c",
            C_ROOT / "src" / "separan_files.c",
            C_ROOT / "src" / "separan_runtime.c",
        ]
        for strict_source in sources[1:3]:
            subprocess.run([
                compiler, "-O1", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I", str(C_ROOT / "include"), "-c", str(strict_source),
                "-o", str(Path(cls.temporary.name) / f"{strict_source.stem}.o"),
            ], check=True)
        subprocess.run([
            compiler, "-O1", "-std=c11", "-Wall", "-Wextra", "-pedantic",
            "-I", str(C_ROOT / "include"), "-o", str(cls.binary),
            *(str(source) for source in sources), "-lm",
            *( ["-lws2_32", "-lpsapi", "-ladvapi32"] if os.name == "nt" else [] ),
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_config_drives_stdio_http_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, body = "ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            config = root / "separan-gw.conf"
            config.write_text(f"# gateway app\nsource = {app}\ntransport = stdio\n", encoding="utf-8")
            request = json.dumps({"method": "GET", "path": "/health"}) + "\n"
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                input=request, text=True, capture_output=True, check=True,
            )
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], 200)
            self.assertEqual(response["body"], "ok")

    def test_unknown_supervisor_setting_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "separan-gw.conf"
            config.write_text("max_workers = 4\n", encoding="utf-8")
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported setting 'max_workers'", result.stderr)

    def test_unknown_transport_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "separan-gw.conf"
            config.write_text("transport = unix\n", encoding="utf-8")
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported transport 'unix'", result.stderr)

    def test_fastcgi_unix_requires_listen_path(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "separan-gw.conf"
            config.write_text("transport = fastcgi-unix\n", encoding="utf-8")
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("fastcgi-unix requires a listen setting", result.stderr)

    def test_help_documents_config(self):
        result = subprocess.run([str(self.binary), "--help"], text=True, capture_output=True, check=True)
        self.assertIn("--config <separan-gw.conf>", result.stdout)

    def test_fastcgi_stdio_request_returns_http_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, content_type = "text/plain", body = "ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            config = root / "separan-gw.conf"
            config.write_text(f"source = {app}\ntransport = fastcgi-stdio\n", encoding="utf-8")
            params = fcgi_params({"REQUEST_METHOD": "GET", "PATH_INFO": "/health", "QUERY_STRING": ""})
            request = b"".join((
                fcgi_record(1, 1, b"\x00\x01\x00\x00\x00\x00\x00\x00"),
                fcgi_record(4, 1, params),
                fcgi_record(4, 1),
                fcgi_record(5, 1),
            ))
            result = subprocess.run(
                [str(self.binary), "--config", str(config)],
                input=request, capture_output=True, check=True,
            )
            records = parse_fcgi_records(result.stdout)
            stdout = b"".join(content for kind, request_id, content in records if kind == 6 and request_id == 1)
            self.assertIn(b"Status: 200\r\n", stdout, (records, result.stderr))
            self.assertIn(b"Content-Type: text/plain\r\n", stdout)
            self.assertTrue(stdout.endswith(b"\r\n\r\nok"), stdout)
            self.assertTrue(any(kind == 7 and request_id == 1 and not content for kind, request_id, content in records))
            self.assertTrue(any(kind == 3 and request_id == 1 for kind, request_id, _ in records))

    @unittest.skipIf(os.name == "nt", "Unix-domain socket listener is POSIX-only")
    def test_fastcgi_unix_socket_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, body = "socket-ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            socket_path = root / "gw.sock"
            config = root / "separan-gw.conf"
            config.write_text(
                f"source = {app}\ntransport = fastcgi-unix\nlisten = unix:{socket_path}\n",
                encoding="utf-8",
            )
            process = subprocess.Popen([str(self.binary), "--config", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        client.connect(str(socket_path))
                        break
                    except (FileNotFoundError, ConnectionRefusedError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail("gateway Unix socket did not become ready")
                        time.sleep(0.02)
                params = fcgi_params({"REQUEST_METHOD": "GET", "PATH_INFO": "/health", "QUERY_STRING": ""})
                request = b"".join((
                    fcgi_record(1, 7, b"\x00\x01\x00\x00\x00\x00\x00\x00"),
                    fcgi_record(4, 7, params), fcgi_record(4, 7), fcgi_record(5, 7),
                ))
                client.sendall(request); client.shutdown(socket.SHUT_WR)
                chunks = []
                while True:
                    chunk = client.recv(65536)
                    if not chunk: break
                    chunks.append(chunk)
                records = parse_fcgi_records(b"".join(chunks))
                stdout = b"".join(content for kind, request_id, content in records if kind == 6 and request_id == 7)
                self.assertIn(b"Status: 200\r\n", stdout)
                self.assertTrue(stdout.endswith(b"\r\n\r\nsocket-ok"), stdout)
                self.assertTrue(any(kind == 3 and request_id == 7 for kind, request_id, _ in records))
            finally:
                client.close()
                process.terminate()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    @unittest.skipIf(os.name == "nt", "POSIX prefork supervisor is POSIX-only")
    def test_fastcgi_unix_supervisor_recycles_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, body = "worker-ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            socket_path = root / "gw.sock"
            config = root / "separan-gw.conf"
            config.write_text(
                f"source = {app}\ntransport = fastcgi-unix\nlisten = unix:{socket_path}\n"
                "workers = 2\nmax_memory = 256M\nmax_requests = 1\nrestart_backoff = 10ms\nrestart_grace = 1s\n",
                encoding="utf-8",
            )
            process = subprocess.Popen([str(self.binary), "--config", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for index in range(4):
                    request_id = 20 + index
                    deadline = time.monotonic() + 5
                    while True:
                        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        try:
                            client.connect(str(socket_path))
                            params = fcgi_params({"REQUEST_METHOD": "GET", "PATH_INFO": "/health", "QUERY_STRING": ""})
                            request = b"".join((
                                fcgi_record(1, request_id, b"\x00\x01\x00\x00\x00\x00\x00\x00"),
                                fcgi_record(4, request_id, params), fcgi_record(4, request_id), fcgi_record(5, request_id),
                            ))
                            client.sendall(request); client.shutdown(socket.SHUT_WR)
                            chunks = []
                            while True:
                                chunk = client.recv(65536)
                                if not chunk: break
                                chunks.append(chunk)
                            records = parse_fcgi_records(b"".join(chunks))
                            stdout = b"".join(content for kind, actual_id, content in records if kind == 6 and actual_id == request_id)
                            self.assertIn(b"Status: 200\r\n", stdout)
                            self.assertTrue(stdout.endswith(b"\r\n\r\nworker-ok"), stdout)
                            self.assertTrue(any(kind == 3 and actual_id == request_id for kind, actual_id, _ in records))
                            break
                        except (ConnectionRefusedError, FileNotFoundError, ConnectionResetError):
                            if process.poll() is not None or time.monotonic() >= deadline:
                                self.fail("supervisor did not replace a recycled worker")
                            time.sleep(0.02)
                        finally:
                            client.close()
                process.terminate()
                process.wait(timeout=5)
                self.assertFalse(socket_path.exists())
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    @unittest.skipIf(os.name == "nt", "POSIX exec reload is POSIX-only")
    def test_fastcgi_unix_sighup_reloads_configured_source(self):
        import signal

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            socket_path = root / "gw.sock"
            config = root / "separan-gw.conf"

            def write_app(body):
                app.write_text(
                    'http_route GET "/health" :health\n'
                    f'return_http(status = 200, body = "{body}")\n'
                    'end_http_route:health\n',
                    encoding="utf-8",
                )

            def request_body(expected, request_id):
                deadline = time.monotonic() + 5
                while True:
                    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        client.connect(str(socket_path))
                        params = fcgi_params({"REQUEST_METHOD": "GET", "PATH_INFO": "/health", "QUERY_STRING": ""})
                        request = b"".join((
                            fcgi_record(1, request_id, b"\x00\x01\x00\x00\x00\x00\x00\x00"),
                            fcgi_record(4, request_id, params), fcgi_record(4, request_id), fcgi_record(5, request_id),
                        ))
                        client.sendall(request); client.shutdown(socket.SHUT_WR)
                        chunks = []
                        while True:
                            chunk = client.recv(65536)
                            if not chunk: break
                            chunks.append(chunk)
                        records = parse_fcgi_records(b"".join(chunks))
                        response = b"".join(content for kind, actual_id, content in records if kind == 6 and actual_id == request_id)
                        if expected.encode() in response:
                            return
                    except (ConnectionRefusedError, FileNotFoundError, ConnectionResetError):
                        pass
                    finally:
                        client.close()
                    if time.monotonic() >= deadline:
                        self.fail(f"gateway did not serve reloaded source body {expected!r}")
                    time.sleep(0.02)

            write_app("before-reload")
            config.write_text(
                f"source = {app}\ntransport = fastcgi-unix\nlisten = unix:{socket_path}\n"
                "workers = 2\nmax_requests = 100\nrestart_backoff = 10ms\nrestart_grace = 1s\n",
                encoding="utf-8",
            )
            process = subprocess.Popen([str(self.binary), "--config", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                request_body("before-reload", 30)
                write_app("after-reload")
                process.send_signal(signal.SIGHUP)
                request_body("after-reload", 31)
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    def test_fastcgi_tcp_listener(self):
        import signal

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, body = "tcp-ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            config = root / "separan-gw.conf"
            config.write_text(
                f"source = {app}\ntransport = fastcgi-tcp\nlisten = tcp:127.0.0.1:{port}\n"
                "workers = 2\nmax_memory = 256M\nmax_requests = 1\nrestart_backoff = 10ms\nrestart_grace = 1s\n",
                encoding="utf-8",
            )
            process = subprocess.Popen(
                [str(self.binary), "--config", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            try:
                for request_id in range(9, 12):
                    deadline = time.monotonic() + 5
                    while True:
                        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        try:
                            client.settimeout(2)
                            client.connect(("127.0.0.1", port))
                            params = fcgi_params({"REQUEST_METHOD": "GET", "PATH_INFO": "/health", "QUERY_STRING": ""})
                            request = b"".join((
                                fcgi_record(1, request_id, b"\x00\x01\x00\x00\x00\x00\x00\x00"),
                                fcgi_record(4, request_id, params), fcgi_record(4, request_id), fcgi_record(5, request_id),
                            ))
                            client.sendall(request); client.shutdown(socket.SHUT_WR)
                            chunks = []
                            while True:
                                chunk = client.recv(65536)
                                if not chunk: break
                                chunks.append(chunk)
                            records = parse_fcgi_records(b"".join(chunks))
                            stdout = b"".join(content for kind, record_id, content in records if kind == 6 and record_id == request_id)
                            self.assertIn(b"Status: 200\r\n", stdout)
                            self.assertTrue(stdout.endswith(b"\r\n\r\ntcp-ok"), stdout)
                            self.assertTrue(any(kind == 3 and record_id == request_id for kind, record_id, _ in records))
                            break
                        except (ConnectionRefusedError, ConnectionResetError, TimeoutError):
                            if process.poll() is not None or time.monotonic() >= deadline:
                                self.fail("gateway TCP supervisor did not replace a worker")
                            time.sleep(0.02)
                        finally:
                            client.close()
            finally:
                if process.poll() is None:
                    if os.name == "nt": process.send_signal(signal.CTRL_BREAK_EVENT)
                    else: process.terminate()
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()

    @unittest.skipUnless(os.name == "nt", "Windows named pipe listener is Windows-only")
    def test_fastcgi_named_pipe_listener(self):
        import ctypes
        import signal

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app.sep"
            app.write_text(
                'http_route GET "/health" :health\n'
                'return_http(status = 200, body = "pipe-ok")\n'
                'end_http_route:health\n',
                encoding="utf-8",
            )
            pipe_name = f"separan-gw-test-{os.getpid()}"
            pipe_path = rf"\\.\pipe\{pipe_name}"
            config = root / "separan-gw.conf"
            config.write_text(
                f"source = {app}\ntransport = fastcgi-pipe\nlisten = pipe:{pipe_name}\n"
                "workers = 2\nmax_memory = 256M\nmax_requests = 1\nrestart_backoff = 10ms\nrestart_grace = 1s\n",
                encoding="utf-8",
            )
            process = subprocess.Popen(
                [str(self.binary), "--config", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateFileW.restype = ctypes.c_void_p
            kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                             ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
            kernel32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
            kernel32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                           ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            invalid_handle = ctypes.c_void_p(-1).value

            def read_exact_pipe(handle, length):
                data = bytearray()
                while len(data) < length:
                    buffer = ctypes.create_string_buffer(length - len(data))
                    received = ctypes.c_uint32()
                    self.assertTrue(kernel32.ReadFile(handle, buffer, len(buffer), ctypes.byref(received), None))
                    self.assertGreater(received.value, 0)
                    data.extend(buffer.raw[:received.value])
                return bytes(data)

            def write_all_pipe(handle, data):
                offset = 0
                while offset < len(data):
                    buffer = ctypes.create_string_buffer(data[offset:])
                    written = ctypes.c_uint32()
                    self.assertTrue(kernel32.WriteFile(handle, buffer, len(data) - offset, ctypes.byref(written), None))
                    self.assertGreater(written.value, 0)
                    offset += written.value

            try:
                for request_id in range(11, 14):
                    deadline = time.monotonic() + 5
                    handle = invalid_handle
                    while handle == invalid_handle or handle is None:
                        handle = kernel32.CreateFileW(pipe_path, 0x80000000 | 0x40000000, 0, None, 3, 0, None)
                        if handle != invalid_handle and handle is not None:
                            break
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail("gateway named-pipe worker was not available")
                        kernel32.WaitNamedPipeW(pipe_path, 100)
                    try:
                        params = fcgi_params({"REQUEST_METHOD": "GET", "PATH_INFO": "/health", "QUERY_STRING": ""})
                        request = b"".join((
                            fcgi_record(1, request_id, b"\x00\x01\x00\x00\x00\x00\x00\x00"),
                            fcgi_record(4, request_id, params), fcgi_record(4, request_id), fcgi_record(5, request_id),
                        ))
                        write_all_pipe(handle, request)
                        data = bytearray()
                        while True:
                            header = read_exact_pipe(handle, 8)
                            data.extend(header)
                            _, record_type, actual_id, content_length, padding_length, _ = struct.unpack(">BBHHBB", header)
                            data.extend(read_exact_pipe(handle, content_length + padding_length))
                            if record_type == 3 and actual_id == request_id:
                                break
                        records = parse_fcgi_records(bytes(data))
                        stdout = b"".join(content for kind, actual_id, content in records if kind == 6 and actual_id == request_id)
                        self.assertIn(b"Status: 200\r\n", stdout)
                        self.assertTrue(stdout.endswith(b"\r\n\r\npipe-ok"), stdout)
                    finally:
                        kernel32.CloseHandle(handle)
            finally:
                if process.poll() is None:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=5)
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
