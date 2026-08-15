import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.ast_printer import format_ast
from separan.lexer import Lexer
from separan.lsp import (
    Server, TOKEN_MODIFIERS, TOKEN_TYPES, completions, definition, diagnostic,
    document_symbols, folding_ranges, highlights, hover, inlay_hints, label_edits,
    semantic_tokens, signature_help,
    structural_scope_at,
)
from separan.lsp_analysis import format_source, variables
from separan.parser import Parser


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

    def test_unicode_labels_appear_in_symbols_and_folding(self):
        source = SOURCE.replace("active", "利用者確認")
        self.assertEqual(diagnostic(source, "file:///unicode.sep"), [])
        symbols = document_symbols(source)
        self.assertEqual(symbols[0]["children"][0]["name"], "利用者確認")
        self.assertIn({"startLine": 1, "endLine": 3, "kind": "region"}, folding_ranges(source))

    def test_initialize_capabilities_and_document_updates(self):
        output = io.BytesIO()
        server = Server(io.BytesIO(), output)
        initialized = server.dispatch({"method": "initialize", "params": {}})
        self.assertTrue(initialized["capabilities"]["documentSymbolProvider"])
        self.assertTrue(initialized["capabilities"]["hoverProvider"])
        self.assertTrue(initialized["capabilities"]["renameProvider"]["prepareProvider"])
        self.assertTrue(initialized["capabilities"]["semanticTokensProvider"]["full"])
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

    def test_label_hover_matching_definition_and_scoped_rename(self):
        source = '''function:main
if true :same
print "first"
endif:same
if true :same
print "second"
endif:same
end_function:main
'''
        label_hover = hover(source, 1, 11)
        self.assertIn("Block: `if`", label_hover["contents"]["value"])
        self.assertIn("Parent: `main`", label_hover["contents"]["value"])
        self.assertEqual(len(highlights(source, 1, 11)), 2)
        self.assertEqual(definition(source, 3, 8, "file:///x.sep")["range"]["start"]["line"], 1)
        edits = label_edits(source, 1, 11, "first_block", "file:///x.sep")["changes"]["file:///x.sep"]
        self.assertEqual(len(edits), 2)
        self.assertEqual({edit["range"]["start"]["line"] for edit in edits}, {1, 3})
        self.assertIsNone(label_edits(source, 0, 10, "renamed_main", "file:///x.sep"))

    def test_variable_hover_definition_members_and_secret_redaction(self):
        source = '''const count = 10
secret = secret_get("token")
object:user
name = "Alice"
age = 30
end_object:user
print count
print user
'''
        value = hover(source, 6, 7)["contents"]["value"]
        self.assertIn("Type: `number`", value); self.assertIn("Mutable: no", value)
        self.assertEqual(definition(source, 6, 7, "file:///x.sep")["range"]["start"]["line"], 0)
        self.assertIn("Value: `<redacted>`", hover(source, 1, 2)["contents"]["value"])
        object_hover = hover(source, 7, 7)["contents"]["value"]
        self.assertIn("`name`: string", object_hover); self.assertIn("`age`: number", object_hover)

    def test_variable_definition_respects_function_scope(self):
        source = '''function:first
value = 1
print value
end_function:first
function:second
value = "two"
print value
end_function:second
'''
        first = definition(source, 2, 7, "file:///x.sep")["range"]["start"]["line"]
        second = definition(source, 6, 7, "file:///x.sep")["range"]["start"]["line"]
        self.assertEqual((first, second), (1, 5))
        reassigned = 'x = 1\nx = 2\nprint x\n'
        self.assertEqual(definition(reassigned, 2, 7, "file:///x.sep")["range"]["start"]["line"], 0)

    def test_completion_signature_help_and_inlay_hints(self):
        source = 'function:main\nif true :active\nend\n'
        labels = [item["label"] for item in completions(source, 2, 3)["items"]]
        self.assertEqual(labels[0], "endif:active")
        self.assertIn("substring", labels)
        self.assertIn("starts_with", labels)
        signature = signature_help('print substring("abc", ', 0, 23)
        self.assertIn("end?: number", signature["signatures"][0]["label"])
        user_signature = signature_help('function:add(a, b)\nend_function:add\nprint add(1, ', 2, 13)
        self.assertIn("add(a, b)", user_signature["signatures"][0]["label"])
        hints = inlay_hints('count = 10\nname = "Alice"\n', {"start": {"line": 0}, "end": {"line": 2}})
        self.assertEqual([hint["label"] for hint in hints], [": number", ": string"])

    def test_structural_end_and_tag_completion(self):
        source = 'function:main\n@notification\nif true :active\n:end\n'
        items = completions(source, 3, 4)["items"]
        self.assertEqual([item["label"] for item in items[:2]], ["endif:active", "end_function:main"])
        self.assertEqual(items[0]["textEdit"]["newText"], "endif:active")
        self.assertIn("opened at line 3", items[0]["detail"])
        tags = completions(source + 'function:other\n@not', 5, 4)["items"]
        self.assertEqual(tags[0]["label"], "@notification")

    def test_readable_math_signatures_and_number_literal_hints(self):
        source = "binary = 0b1111_0000\nhexadecimal = 0xff_ff\naverage = moving_average([1, 2, 3], 2)\n"
        hints = inlay_hints(source, {"start": {"line": 0}, "end": {"line": 3}})
        self.assertEqual([hint["label"] for hint in hints], [": number", ": number", ": list"])
        signature = signature_help("print percentile([1, 2, 3], ", 0, 31)
        self.assertIn("percent: number", signature["signatures"][0]["label"])
        math_hover = hover("print square_root(16)\n", 0, 10)
        self.assertIn("square_root(value: number)", math_hover["contents"]["value"])
        labels = [item["label"] for item in completions("print square_", 0, 13)["items"]]
        self.assertIn("square_root", labels)

    def test_embedded_pin_completion_hover_and_signatures(self):
        source = 'board = board_select("raspberry_pi_pico")\nprint pin.A\n'
        items = completions(source, 1, 11)["items"]
        self.assertEqual([item["label"] for item in items], ["A0", "A1", "A2"])
        hover_value = hover(source.replace("pin.A", "pin.A0"), 1, 10)["contents"]["value"]
        self.assertIn("GPIO26", hover_value)
        self.assertIn("analog_input", hover_value)
        signature = signature_help("print i2c_open(0, ", 0, 19)
        self.assertIn("sda?: pin", signature["signatures"][0]["label"])

    def test_network_completion_signatures_and_inferred_types(self):
        labels = [item["label"] for item in completions("print network_", 0, 14)["items"]]
        self.assertIn("network_interfaces", labels)
        self.assertIn("network_preferred_interface", labels)
        signature = signature_help('print tcp_connect("example.com", 443, ', 0, 39)
        self.assertIn("timeout?: duration", signature["signatures"][0]["label"])
        inferred = {item.name: item.type for item in variables('''address = ip_address("192.0.2.1")
interfaces = network_interfaces()
tcp = tcp_connect("example.test", 443)
udp = udp_open()
packet = udp_receive(udp)
''')}
        self.assertEqual(inferred, {
            "address": "ip_address", "interfaces": "list", "tcp": "tcp_connection",
            "udp": "udp_socket", "packet": "object",
        })

    def test_semantic_tokens_include_typed_variables_parameters_and_labels(self):
        source = '''function:main(value)
const count = 10
if true :active
print count
endif:active
end_function:main
'''
        encoded = semantic_tokens(source)["data"]; decoded = []; line = start = 0
        for index in range(0, len(encoded), 5):
            delta_line, delta_start, length, token_type, modifiers = encoded[index:index + 5]
            line += delta_line; start = start + delta_start if delta_line == 0 else delta_start
            decoded.append((line, start, length, TOKEN_TYPES[token_type], modifiers))
        self.assertTrue(any(item[3] == "label" for item in decoded))
        count_token = next(item for item in decoded if item[0] == 1 and item[3] == "variable")
        self.assertTrue(count_token[4] & (1 << TOKEN_MODIFIERS.index("number")))
        self.assertTrue(count_token[4] & (1 << TOKEN_MODIFIERS.index("readonly")))
        self.assertTrue(any(item[3] == "parameter" for item in decoded))
        conflict = semantic_tokens('name = "name"\nprint "name"\n')["data"]
        conflict_types = [TOKEN_TYPES[conflict[index + 3]] for index in range(0, len(conflict), 5)]
        self.assertEqual(conflict_types.count("variable"), 1)
        self.assertEqual(conflict_types.count("string"), 2)

    def test_static_type_diagnostic_and_mismatch_quick_fix(self):
        errors = diagnostic('x = 10\nx = "wrong"\n', "file:///type.sep")
        self.assertEqual(errors[0]["code"], "E201")
        mismatch = diagnostic(SOURCE.replace("endif:active", "endif:wrong"), "file:///label.sep")[0]
        self.assertEqual(mismatch["data"]["replacement"], "active")
        server = Server(io.BytesIO(), io.BytesIO())
        actions = server.dispatch({"method": "textDocument/codeAction", "params": {"textDocument": {"uri": "file:///label.sep"}, "context": {"diagnostics": [mismatch]}}})
        self.assertEqual(actions[0]["title"], "Replace with endif:active")
        self.assertEqual(actions[0]["edit"]["changes"]["file:///label.sep"][0]["newText"], "active")
        kind = diagnostic('function:main\nif true :active\nendwhile:active\nend_function:main\n', "file:///kind.sep")[0]
        self.assertEqual(kind["code"], "E105")
        self.assertEqual(kind["data"]["replacement"], "endif:active")

    def test_formatter_preserves_structural_ast(self):
        source = 'function:main\nif true :x\nprint "ok"\nelse:x\nprint "no"\nendif:x\nend_function:main\n'
        formatted = format_source(source)
        before = format_ast(Parser(Lexer(source).scan_tokens()).parse())
        after = format_ast(Parser(Lexer(formatted).scan_tokens()).parse())
        self.assertEqual(before, after)
        self.assertIn('        print "ok"', formatted)

    def test_multiline_comment_content_is_not_editor_structure(self):
        source = '''function:main
##note
if true :fake
endif:fake
##note
if true :real # inline comment
endif:real
end_function:main
'''
        symbols = document_symbols(source)
        self.assertEqual([item["name"] for item in symbols[0]["children"]], ["real"])
        formatted = format_source(source)
        self.assertIn("    if true :fake", formatted)
        self.assertTrue(Parser(Lexer(formatted).scan_tokens()).parse())

    def test_v04_structural_requests_use_parser_block_identity(self):
        scope = structural_scope_at(SOURCE, 1, 11, "file:///x.sep")
        self.assertEqual(scope["path"], "function:main#1/if:active#1")
        server = Server(io.BytesIO(), io.BytesIO())
        changed_inside = SOURCE.replace('print "ok"', 'print "changed"')
        verified = server.dispatch({"method": "separan/verifyScope", "params": {
            "uri": "file:///x.sep", "before": SOURCE, "after": changed_inside,
            "scopes": [scope["path"]],
        }})
        self.assertTrue(verified["passed"])
        changed_outside = SOURCE.replace("function:main", "function:renamed").replace("end_function:main", "end_function:renamed")
        rejected = server.dispatch({"method": "separan/verifyScope", "params": {
            "uri": "file:///x.sep", "before": SOURCE, "after": changed_outside,
            "scopes": [scope["path"]],
        }})
        self.assertFalse(rejected["passed"])

    def test_v05_document_structure_request_exposes_human_insights(self):
        source = '''function:main
value = load(source)
if value != null :loaded
print value
endif:loaded
end_function:main
'''
        server = Server(io.BytesIO(), io.BytesIO()); uri = "file:///structure.sep"
        server.documents[uri] = source
        report = server.dispatch({"method": "separan/documentStructure", "params": {"textDocument": {"uri": uri}}})
        function = report["roots"][0]
        self.assertEqual(report["schema"], "separan.document-structure.v2")
        self.assertEqual(function["reads"], ["source"])
        self.assertEqual(function["writes"], ["value"])
        self.assertEqual(function["calls"], ["load"])
        self.assertEqual(function["children"][0]["reads"], ["value"])


if __name__ == "__main__": unittest.main()
