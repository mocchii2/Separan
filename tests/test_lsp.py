import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.lsp import Server, diagnostic, document_symbols, folding_ranges


SOURCE = '''function:main
if true :active
print "ok"
endif:active
end_function:main
'''


class LspTests(unittest.TestCase):
    def test_parser_diagnostic_uses_zero_based_lsp_position(self):
        errors = diagnostic(SOURCE.replace("endif:active", "endif:wrong"), "file:///test.sep")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["code"], "E104")
        self.assertEqual(errors[0]["range"]["start"], {"line": 3, "character": 6})
        self.assertEqual(errors[0]["source"], "separan")

    def test_document_symbols_preserve_block_hierarchy(self):
        symbols = document_symbols(SOURCE)
        self.assertEqual([(item["name"], item["detail"]) for item in symbols], [("main", "function")])
        self.assertEqual(symbols[0]["children"][0]["name"], "active")
        self.assertEqual(symbols[0]["range"]["end"]["line"], 4)

    def test_folding_ranges_include_nested_labeled_blocks(self):
        self.assertEqual(folding_ranges(SOURCE), [
            {"startLine": 0, "endLine": 4, "kind": "region"},
            {"startLine": 1, "endLine": 3, "kind": "region"},
        ])

    def test_initialize_capabilities_and_document_updates(self):
        output = io.BytesIO()
        server = Server(io.BytesIO(), output)
        initialized = server.dispatch({"method": "initialize", "params": {}})
        self.assertTrue(initialized["capabilities"]["documentSymbolProvider"])
        server.dispatch({"method": "textDocument/didOpen", "params": {"textDocument": {"uri": "file:///test.sep", "text": SOURCE}}})
        payload = output.getvalue().split(b"\r\n\r\n", 1)[1]
        notification = json.loads(payload)
        self.assertEqual(notification["params"]["diagnostics"], [])

    def test_stdio_json_rpc_framing(self):
        request = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}}).encode()
        reader = io.BytesIO(f"Content-Length: {len(request)}\r\n\r\n".encode() + request)
        writer = io.BytesIO()
        self.assertEqual(Server(reader, writer).run(), 0)
        header, payload = writer.getvalue().split(b"\r\n\r\n", 1)
        self.assertEqual(header, f"Content-Length: {len(payload)}".encode())
        self.assertEqual(json.loads(payload)["id"], 7)


if __name__ == "__main__": unittest.main()
