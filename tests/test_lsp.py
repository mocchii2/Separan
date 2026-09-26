import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.ast_printer import format_ast
from separan.errors import SeparanError
from separan.lexer import Lexer
from separan.lsp import (
    Server, TOKEN_MODIFIERS, TOKEN_TYPES, completions, definition, diagnostic,
    document_symbols, folding_ranges, highlights, hover, inlay_hints, label_edits,
    semantic_tokens, signature_help,
    structural_scope_at,
)
from separan.lsp_analysis import format_source, variables
from separan.parser import Parser


SOURCE = '''SEP:main
if true :active
print "ok"
endif:active
END_SEP:main
'''


class LspTests(unittest.TestCase):
    def test_parser_diagnostic_uses_zero_based_lsp_position(self):
        errors = diagnostic(SOURCE.replace("endif:active", "endif:wrong"), "file:///test.sep")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["code"], "E104")
        self.assertEqual(errors[0]["range"]["start"], {"line": 3, "character": 6})
        self.assertEqual(errors[0]["source"], "separan")

    def test_parser_recovery_reports_independent_function_errors(self):
        source = '''SEP:first
print (1 + )
END_SEP:first
SEP:second
print (2 + )
END_SEP:second
'''
        errors = diagnostic(source, "file:///recovery.sep")
        self.assertEqual([item["code"] for item in errors], ["E100", "E100"])
        self.assertEqual([item["range"]["start"]["line"] for item in errors], [1, 4])
        with self.assertRaises(SeparanError):
            Parser(Lexer(source, "recovery.sep").scan_tokens()).parse()

    def test_parser_recovery_keeps_next_declaration_after_late_import(self):
        source = '''value = 1
import "late.sep" as late
SEP:second
print (2 + )
END_SEP:second
'''
        errors = diagnostic(source, "file:///late-import-recovery.sep")
        self.assertEqual([item["code"] for item in errors], ["E702", "E100"])

    def test_document_symbols_preserve_block_hierarchy(self):
        symbols = document_symbols(SOURCE)
        self.assertEqual([(item["name"], item["detail"]) for item in symbols], [("main", "SEP")])
        self.assertEqual(symbols[0]["children"][0]["name"], "active")
        self.assertEqual(symbols[0]["range"]["end"]["line"], 4)

    def test_folding_ranges_include_nested_labeled_blocks(self):
        self.assertEqual(folding_ranges(SOURCE), [
            {"startLine": 0, "endLine": 4, "kind": "region"},
            {"startLine": 1, "endLine": 3, "kind": "region"},
        ])

    def test_sep_is_the_canonical_block_name_in_lsp(self):
        source = '''SEP:main
if true :active
print "ok"
endif:active
END_SEP:main
'''
        symbols = document_symbols(source)
        self.assertEqual([(item["name"], item["detail"]) for item in symbols], [("main", "SEP")])
        self.assertIn("END_SEP:main", [item["label"] for item in completions(source, 2, 4)["items"]])

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
        self.assertTrue(initialized["capabilities"]["referencesProvider"])
        self.assertTrue(initialized["capabilities"]["renameProvider"]["prepareProvider"])
        self.assertTrue(initialized["capabilities"]["semanticTokensProvider"]["full"])
        server.dispatch({"method": "textDocument/didOpen", "params": {"textDocument": {"uri": "file:///test.sep", "text": SOURCE}}})
        payload = output.getvalue().split(b"\r\n\r\n", 1)[1]
        notification = json.loads(payload)
        self.assertEqual(notification["params"]["diagnostics"], [])

    def test_workspace_references_resolve_imported_function_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_path = root / "math.sep"
            caller_path = root / "app.sep"
            module_source = "SEP:add(a, b)\nreturn a + b\nEND_SEP:add\n"
            caller_source = '''import "math.sep" as math
SEP:main
print math.add(1, 2)
print math.add(3, 4)
print "math.add"
# math.add(5, 6)
END_SEP:main
'''
            module_path.write_text(module_source, encoding="utf-8")
            caller_path.write_text(caller_source, encoding="utf-8")
            module_uri, caller_uri = module_path.as_uri(), caller_path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "references"}],
            }})
            server.documents[caller_uri] = caller_source
            call_line = caller_source.splitlines()[2]
            references = server.dispatch({"method": "textDocument/references", "params": {
                "textDocument": {"uri": caller_uri},
                "position": {"line": 2, "character": call_line.index("add") + 1},
                "context": {"includeDeclaration": True},
            }})
            self.assertEqual(references, [
                {"uri": module_uri, "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}}},
                {"uri": caller_uri, "range": {"start": {"line": 2, "character": 11}, "end": {"line": 2, "character": 14}}},
                {"uri": caller_uri, "range": {"start": {"line": 3, "character": 11}, "end": {"line": 3, "character": 14}}},
            ])
            calls_only = server.dispatch({"method": "textDocument/references", "params": {
                "textDocument": {"uri": caller_uri},
                "position": {"line": 2, "character": call_line.index("add") + 1},
                "context": {"includeDeclaration": False},
            }})
            self.assertEqual(calls_only, references[1:])

    def test_signature_help_infers_imported_function_parameter_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_path = root / "math.sep"
            caller_path = root / "app.sep"
            peer_path = root / "peer.sep"
            module_path.write_text(
                "SEP:combine(left: number, right)\nreturn left\nEND_SEP:combine\n", encoding="utf-8",
            )
            caller_source = '''import "math.sep" as math
SEP:main
print math.combine(unknown_left, unknown_right)
END_SEP:main
'''
            peer_path.write_text('''import "math.sep" as functions
SEP:main
number_value = 1
text_value = "value"
print functions.combine(number_value, text_value)
END_SEP:main
''', encoding="utf-8")
            caller_path.write_text(caller_source, encoding="utf-8")
            caller_uri = caller_path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "inference"}],
            }})
            server.documents[caller_uri] = caller_source
            call_line = caller_source.splitlines()[2]
            response = server.dispatch({"method": "textDocument/signatureHelp", "params": {
                "textDocument": {"uri": caller_uri},
                "position": {"line": 2, "character": call_line.index("math.combine(") + len("math.combine(")},
            }})
            self.assertEqual(
                response["signatures"][0]["label"],
                "combine(left: number, right: string) -> inferred",
            )

    def test_semantic_tag_rename_updates_workspace_files_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "first.sep"
            second_path = root / "second.sep"
            first_source = "SEP:first\n@notification\nEND_SEP:first\n"
            second_source = '''SEP:second
@notification
print "@notification"
# @notification
END_SEP:second
'''
            first_path.write_text(first_source, encoding="utf-8")
            second_path.write_text(second_source, encoding="utf-8")
            first_uri, second_uri = first_path.as_uri(), second_path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "tags"}],
            }})
            server.documents[first_uri] = first_source
            edits = server.dispatch({"method": "textDocument/rename", "params": {
                "textDocument": {"uri": first_uri},
                "position": {"line": 1, "character": 3},
                "newName": "alerts:mail",
            }})
            self.assertEqual(edits, {"changes": {
                first_uri: [{"range": {"start": {"line": 1, "character": 1}, "end": {"line": 1, "character": 13}}, "newText": "alerts:mail"}],
                second_uri: [{"range": {"start": {"line": 1, "character": 1}, "end": {"line": 1, "character": 13}}, "newText": "alerts:mail"}],
            }})

    def test_semantic_tag_rename_rejects_same_function_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = "SEP:main\n@notification\n@alerts\nEND_SEP:main\n"
            path = root / "main.sep"
            path.write_text(source, encoding="utf-8")
            uri = path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "tag-collision"}],
            }})
            server.documents[uri] = source
            self.assertIsNone(server.dispatch({"method": "textDocument/rename", "params": {
                "textDocument": {"uri": uri}, "position": {"line": 1, "character": 3},
                "newName": "alerts",
            }}))

    def test_call_hierarchy_reports_workspace_incoming_and_outgoing_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = '''SEP:leaf(value)
return value
END_SEP:leaf
SEP:main
print leaf(1)
print leaf(2)
END_SEP:main
'''
            path = root / "calls.sep"
            path.write_text(source, encoding="utf-8")
            uri = path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            initialized = server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "calls"}],
            }})
            self.assertTrue(initialized["capabilities"]["callHierarchyProvider"])
            server.documents[uri] = source

            leaf = server.dispatch({"method": "textDocument/prepareCallHierarchy", "params": {
                "textDocument": {"uri": uri}, "position": {"line": 0, "character": 5},
            }})[0]
            incoming = server.dispatch({"method": "callHierarchy/incomingCalls", "params": {"item": leaf}})
            self.assertEqual([(item["from"]["name"], len(item["fromRanges"])) for item in incoming], [("main", 2)])

            main = server.dispatch({"method": "textDocument/prepareCallHierarchy", "params": {
                "textDocument": {"uri": uri}, "position": {"line": 3, "character": 5},
            }})[0]
            outgoing = server.dispatch({"method": "callHierarchy/outgoingCalls", "params": {"item": main}})
            self.assertEqual([(item["to"]["name"], len(item["fromRanges"])) for item in outgoing], [("leaf", 2)])

    def test_call_hierarchy_resolves_imported_module_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_path = root / "module.sep"
            caller_path = root / "caller.sep"
            module_path.write_text("SEP:helper(value)\nreturn value\nEND_SEP:helper\n", encoding="utf-8")
            caller_source = '''import "module.sep" as module
SEP:main
print module.helper(1)
END_SEP:main
'''
            caller_path.write_text(caller_source, encoding="utf-8")
            uri = caller_path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "module-calls"}],
            }})
            server.documents[uri] = caller_source
            helper = server.dispatch({"method": "textDocument/prepareCallHierarchy", "params": {
                "textDocument": {"uri": uri}, "position": {"line": 2, "character": 15},
            }})[0]
            self.assertEqual(helper["name"], "helper")
            incoming = server.dispatch({"method": "callHierarchy/incomingCalls", "params": {"item": helper}})
            self.assertEqual(incoming[0]["from"]["name"], "main")
            main = server.dispatch({"method": "textDocument/prepareCallHierarchy", "params": {
                "textDocument": {"uri": uri}, "position": {"line": 1, "character": 5},
            }})[0]
            outgoing = server.dispatch({"method": "callHierarchy/outgoingCalls", "params": {"item": main}})
            self.assertEqual(outgoing[0]["to"]["name"], "helper")

    def test_reference_code_lens_counts_workspace_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module_path = root / "math.sep"
            caller_path = root / "app.sep"
            module_source = "SEP:combine(left, right)\nreturn left\nEND_SEP:combine\n"
            caller_source = '''import "math.sep" as math
SEP:main
print math.combine(1, 2)
print math.combine(3, 4)
END_SEP:main
'''
            module_path.write_text(module_source, encoding="utf-8")
            caller_path.write_text(caller_source, encoding="utf-8")
            uri = module_path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "lenses"}],
            }})
            server.documents[uri] = module_source
            lenses = server.dispatch({"method": "textDocument/codeLens", "params": {
                "textDocument": {"uri": uri},
            }})
            self.assertEqual(len(lenses), 1)
            self.assertEqual(lenses[0]["command"]["title"], "2 references")
            self.assertEqual(lenses[0]["command"]["command"], "editor.action.showReferences")
            self.assertEqual(len(lenses[0]["command"]["arguments"][2]), 2)

    def test_run_function_execute_command_invokes_current_source_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "run.sep"
            source = 'SEP:run_me()\nprint "ran"\nEND_SEP:run_me\n'
            path.write_text(source, encoding="utf-8")
            uri = path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "run-function"}],
            }})
            server.documents[uri] = source
            result = server.dispatch({"method": "workspace/executeCommand", "params": {
                "command": "separan.runFunction", "arguments": [uri, "run_me", []],
            }})
            self.assertEqual(result["output"], "ran\n")
            builtin = server.dispatch({"method": "workspace/executeCommand", "params": {
                "command": "separan.runFunction", "arguments": [uri, "length", ["value"]],
            }})
            self.assertIn("Unknown Separan function", builtin["error"])

    def test_test_function_code_lens_is_runnably_labeled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "test_cases.sep"
            source = 'SEP:test_basic()\nprint "passed"\nEND_SEP:test_basic\n'
            path.write_text(source, encoding="utf-8")
            uri = path.as_uri()
            server = Server(io.BytesIO(), io.BytesIO())
            server.dispatch({"method": "initialize", "params": {
                "workspaceFolders": [{"uri": root.as_uri(), "name": "test-lens"}],
            }})
            server.documents[uri] = source
            lenses = server.dispatch({"method": "textDocument/codeLens", "params": {
                "textDocument": {"uri": uri},
            }})
            run_test = next(item for item in lenses if item["command"]["title"] == "Run Test")
            self.assertEqual(run_test["command"]["command"], "separan.runFunction")
            self.assertEqual(run_test["command"]["arguments"], [uri, "test_basic", []])

    @unittest.skipUnless(sys.platform == "win32", "Windows-only URI normalization")
    def test_windows_file_uris_are_readable_by_the_core(self):
        target = ROOT / "tests" / "windows_core_fixture.sep"
        target.write_text(SOURCE, encoding="utf-8")
        self.addCleanup(target.unlink, missing_ok=True)
        self.assertEqual(Server().source(target.as_uri()), SOURCE)

    def test_stdio_json_rpc_framing(self):
        request = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}}).encode()
        reader = io.BytesIO(f"Content-Length: {len(request)}\r\n\r\n".encode() + request)
        writer = io.BytesIO()
        self.assertEqual(Server(reader, writer).run(), 0)
        header, payload = writer.getvalue().split(b"\r\n\r\n", 1)
        self.assertEqual(header, f"Content-Length: {len(payload)}".encode())
        self.assertEqual(json.loads(payload)["id"], 7)

    def test_label_hover_matching_definition_and_scoped_rename(self):
        source = '''SEP:main
if true :same
print "first"
endif:same
if true :same
print "second"
endif:same
END_SEP:main
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
        source = '''SEP:first
value = 1
print value
END_SEP:first
SEP:second
value = "two"
print value
END_SEP:second
'''
        first = definition(source, 2, 7, "file:///x.sep")["range"]["start"]["line"]
        second = definition(source, 6, 7, "file:///x.sep")["range"]["start"]["line"]
        self.assertEqual((first, second), (1, 5))
        reassigned = 'x = 1\nx = 2\nprint x\n'
        self.assertEqual(definition(reassigned, 2, 7, "file:///x.sep")["range"]["start"]["line"], 0)

    def test_completion_signature_help_and_inlay_hints(self):
        source = 'SEP:main\nif true :active\nend\n'
        labels = [item["label"] for item in completions(source, 2, 3)["items"]]
        self.assertEqual(labels[0], "endif:active")
        self.assertIn("substring", labels)
        self.assertIn("starts_with", labels)
        signature = signature_help('print substring("abc", ', 0, 23)
        self.assertIn("end?: number", signature["signatures"][0]["label"])
        oauth_signature = signature_help('token = oauth_client_credentials("https://auth.test/token", ', 0, 61)
        self.assertIn("client_secret: secret", oauth_signature["signatures"][0]["label"])
        user_signature = signature_help('SEP:add(a, b)\nEND_SEP:add\nprint add(1, ', 2, 13)
        self.assertIn("add(a, b)", user_signature["signatures"][0]["label"])
        hints = inlay_hints('count = 10\nname = "Alice"\n', {"start": {"line": 0}, "end": {"line": 2}})
        self.assertEqual([hint["label"] for hint in hints], [": number", ": string"])

    def test_editor_contract_uses_empty_and_void_without_null(self):
        write_signature = signature_help('write_text("out.txt", ', 0, 22)
        self.assertIn("-> VOID", write_signature["signatures"][0]["label"])
        lease_signature = signature_help("network_dhcp_lease(", 0, 19)
        self.assertIn("object | EMPTY", lease_signature["signatures"][0]["label"])
        errors = diagnostic("value = null\n", "file:///legacy.sep")
        self.assertEqual(errors[0]["code"], "E135")

    def test_oauth_static_types_remain_explicit(self):
        source = '''client_secret = secret_from_environment("OAUTH_CLIENT_SECRET")
token = oauth_client_credentials("https://auth.test/token", "client", client_secret)
auth = bearer_auth(token.access_token)
'''
        inferred = {item.name: item.type for item in variables(source)}
        self.assertEqual(inferred, {"client_secret": "secret", "token": "oauth_token", "auth": "http_auth"})

    def test_network_addressing_signatures_and_types(self):
        call = 'network_set_static_address(lan, '
        signature = signature_help(call, 0, len(call))
        self.assertIn("gateway: ip_address", signature["signatures"][0]["label"])
        source = '''mode = network_address_mode(lan)
state = network_dhcp_status(lan)
lease = network_dhcp_lease(lan)
ready = network_wait_until_addressed(lan, duration("10s"))
'''
        inferred = {item.name: item.type for item in variables(source)}
        self.assertEqual(inferred, {"mode": "string", "state": "string", "lease": "object", "ready": "boolean"})

    def test_network_service_signatures_and_types(self):
        signature = signature_help('dhcp_server_start(wifi, server_address = "192.168.4.1", ', 0, 63)
        self.assertIn("pool_start: ip_address", signature["signatures"][0]["label"])
        source = '''dhcp = dhcp_server_start(wifi, server_address = "192.168.4.1", prefix = 24, pool_start = "192.168.4.10", pool_end = "192.168.4.50", lease_time = duration("1h"))
dns = dns_server_start(wifi, server_address = "192.168.4.1", records = records)
state = dhcp_server_status(dhcp)
leases = dhcp_server_leases(dhcp)
ap = wifi_access_point_status(wifi)
'''
        inferred = {item.name: item.type for item in variables(source)}
        self.assertEqual(inferred, {"dhcp": "dhcp_server", "dns": "dns_server", "state": "string", "leases": "list", "ap": "object"})

    def test_structural_end_and_tag_completion(self):
        source = 'SEP:main\n@notification\nif true :active\n:end\n'
        items = completions(source, 3, 4)["items"]
        self.assertEqual([item["label"] for item in items[:2]], ["endif:active", "END_SEP:main"])
        self.assertEqual(items[0]["textEdit"]["newText"], "endif:active")
        self.assertIn("opened at line 3", items[0]["detail"])
        tags = completions(source + 'SEP:other\n@not', 5, 4)["items"]
        self.assertEqual(tags[0]["label"], "@notification")
        hierarchical = 'SEP:first\n@monitor:notification:decision\nEND_SEP:first\nSEP:other\n@monitor:n'
        tags = completions(hierarchical, 4, len("@monitor:n"))["items"]
        self.assertEqual(tags[0]["label"], "@monitor:notification:decision")

    def test_clip_utf8_signature_and_inferred_type(self):
        signature = signature_help('value = clip_utf8("日本語", ', 0, 27)
        self.assertIn("maximum_bytes: number", signature["signatures"][0]["label"])
        inferred = {item.name: item.type for item in variables('value = clip_utf8("日本語", 6)\n')}
        self.assertEqual(inferred["value"], "string")

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
        source = '''SEP:main(value)
const count = 10
if true :active
print count
endif:active
END_SEP:main
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
        kind = diagnostic('SEP:main\nif true :active\nendwhile:active\nEND_SEP:main\n', "file:///kind.sep")[0]
        self.assertEqual(kind["code"], "E105")
        self.assertEqual(kind["data"]["replacement"], "endif:active")

    def test_formatter_preserves_structural_ast(self):
        source = 'SEP:main\nif true :x\nprint "ok"\nelse:x\nprint "no"\nendif:x\nEND_SEP:main\n'
        formatted = format_source(source)
        before = format_ast(Parser(Lexer(source).scan_tokens()).parse())
        after = format_ast(Parser(Lexer(formatted).scan_tokens()).parse())
        self.assertEqual(before, after)
        self.assertIn('        print "ok"', formatted)

    def test_multiline_comment_content_is_not_editor_structure(self):
        source = '''SEP:main
##note
if true :fake
endif:fake
##note
if true :real # inline comment
endif:real
END_SEP:main
'''
        symbols = document_symbols(source)
        self.assertEqual([item["name"] for item in symbols[0]["children"]], ["real"])
        formatted = format_source(source)
        self.assertIn("    if true :fake", formatted)
        self.assertTrue(Parser(Lexer(formatted).scan_tokens()).parse())

    def test_v04_structural_requests_use_parser_block_identity(self):
        scope = structural_scope_at(SOURCE, 1, 11, "file:///x.sep")
        self.assertEqual(scope["path"], "SEP:main#1/if:active#1")
        server = Server(io.BytesIO(), io.BytesIO())
        changed_inside = SOURCE.replace('print "ok"', 'print "changed"')
        verified = server.dispatch({"method": "separan/verifyScope", "params": {
            "uri": "file:///x.sep", "before": SOURCE, "after": changed_inside,
            "scopes": [scope["path"]],
        }})
        self.assertTrue(verified["passed"])
        changed_outside = SOURCE.replace("SEP:main", "SEP:renamed").replace("END_SEP:main", "END_SEP:renamed")
        rejected = server.dispatch({"method": "separan/verifyScope", "params": {
            "uri": "file:///x.sep", "before": SOURCE, "after": changed_outside,
            "scopes": [scope["path"]],
        }})
        self.assertFalse(rejected["passed"])

    def test_v05_document_structure_request_exposes_human_insights(self):
        source = '''SEP:main
string value = load(source)
if value is not EMPTY :loaded
print value
endif:loaded
END_SEP:main
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

    def test_explicit_variable_field_and_parameter_types_are_visible(self):
        source = '''number count = EMPTY
object:user
string name = EMPTY
end_object:user
print user
SEP:show(value: number, items: list<string>)
print type_of(value)
END_SEP:show
'''
        line = source.splitlines()[5]
        value_start = line.index("value")
        items_start = line.index("items")
        self.assertIn("Type: `number`", hover(source, 5, value_start)["contents"]["value"])
        self.assertIn("`name`: string", hover(source, 4, 7)["contents"]["value"])
        self.assertIn("Type: `list`", hover(source, 5, items_start + 2)["contents"]["value"])

    def test_recursive_list_types_and_shape_signatures_are_visible(self):
        source = '''list<list<number>> matrix = [[1], [2, 3]]
SEP:show(rows: list<list<string>>)
print rows
END_SEP:show
'''
        inferred = {item.name: item.type for item in variables(source)}
        self.assertEqual(inferred, {"matrix": "list", "rows": "list"})
        insert = signature_help("list_insert(matrix, ", 0, 20)
        self.assertIn("front | number | back", insert["signatures"][0]["label"])
        vertical = signature_help("list_remove_vertical(matrix, 0, ", 0, 32)
        self.assertIn("fixed_column: number", vertical["signatures"][0]["label"])
        self.assertIn("position: front | number | back", vertical["signatures"][0]["label"])
        horizontal = signature_help("list_remove_horizontal(matrix, 0, ", 0, 34)
        self.assertIn("fixed_row: number", horizontal["signatures"][0]["label"])

    def test_position_selectors_have_semantic_tokens(self):
        source = "list_insert(values, front, 2)\nlist_remove(values, back, 1)\n"
        encoded = semantic_tokens(source)["data"]
        decoded = []
        line = start = 0
        for index in range(0, len(encoded), 5):
            delta_line, delta_start, length, token_type, _ = encoded[index:index + 5]
            line += delta_line
            start = start + delta_start if delta_line == 0 else delta_start
            decoded.append((source.splitlines()[line][start:start + length], TOKEN_TYPES[token_type]))
        self.assertIn(("front", "type"), decoded)
        self.assertIn(("back", "type"), decoded)


if __name__ == "__main__": unittest.main()
