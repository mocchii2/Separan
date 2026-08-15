import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.cli import execute
from separan.errors import SeparanError


class StructuredDataTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "tests" / "fixtures" / "structured_runtime"
        if self.root.exists(): shutil.rmtree(self.root)
        self.root.mkdir()
        self.capability = RuntimeCapabilities.local(self.root)

    def tearDown(self):
        if self.root.exists(): shutil.rmtree(self.root)

    def assert_error(self, source, code, capability=None):
        source = "function:main\n" + source + "end_function:main\n"
        with self.assertRaises(SeparanError) as caught:
            execute(source, capabilities=capability or self.capability)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_yaml_data_mapping_order_unicode_and_explicit_date_string(self):
        source = '''function:main
config = yaml_to_object("environment: production\\ntargets:\\n  - WEB01\\n  - WEB02\\nenabled: true\\nstarted: 2026-08-15\\n")
print config.environment
print config.targets[1]
print config.enabled
print type_of(config.started)
print object_to_yaml(config, indent = 4, sort_keys = false)
end_function:main
'''
        output = execute(source, capabilities=self.capability)[1]
        self.assertIn("production\nWEB02\ntrue\nstring\n", output)
        yaml_text = output.split("string\n", 1)[1]
        self.assertLess(yaml_text.index("environment:"), yaml_text.index("targets:"))
        self.assertIn("started: '2026-08-15'", yaml_text)

    def test_yaml_uses_unambiguous_core_scalar_rules(self):
        source = '''function:main
value = yaml_to_object("yes_value: yes\\nno_value: no\\nleading_zero: 012\\nscientific: 1e3\\n")
print type_of(value.yes_value)
print type_of(value.no_value)
print value.leading_zero
print value.scientific
end_function:main
'''
        self.assertEqual(execute(source)[1], "string\nstring\n12\n1000.0\n")

    def test_yaml_multiple_documents_and_stream_type_rule(self):
        source = '''function:main
documents = yaml_to_objects("---\\nname: one\\n---\\nname: two\\n")
print length(documents)
print documents[1].name
print objects_to_yaml(documents, sort_keys = false)
end_function:main
'''
        output = execute(source)[1]
        self.assertTrue(output.startswith("2\ntwo\n---\nname: one\n---\nname: two\n"))
        self.assert_error('print yaml_to_object("---\\na: 1\\n---\\na: 2\\n")\n', "E940")
        self.assert_error('print yaml_to_objects("---\\na: 1\\n---\\ntext\\n")\n', "E942")

    def test_yaml_rejects_duplicate_non_string_mixed_tag_and_recursive_alias(self):
        cases = (
            ('print yaml_to_object("a: 1\\na: 2\\n")\n', "E940"),
            ('print yaml_to_object("1: value\\n")\n', "E940"),
            ('print yaml_to_object("values: [1, text]\\n")\n', "E942"),
            ('print yaml_to_object("value: !!python/object:builtins.object {}\\n")\n', "E940"),
            ('print yaml_to_object("loop: &loop [*loop]\\n")\n', "E943"),
        )
        for source, code in cases:
            with self.subTest(code=code, source=source): self.assert_error(source, code)

        diagnostic = self.assert_error('print yaml_to_object("root:\\n  broken: [1,\\n")\n', "E940")
        self.assertIn("line 3", diagnostic.actual)

    def test_yaml_file_round_trip_validation_and_capabilities(self):
        source = '''function:main
config = yaml_to_object("name: 監視\\nthreshold: 95\\n")
object_to_yaml_file("config/monitor.yaml", config, indent = 2, sort_keys = false)
print yaml_validate_file("config/monitor.yaml")
loaded = yaml_file_to_object("config/monitor.yaml")
print loaded.name
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability)[1], "true\n監視\n")
        self.assertTrue((self.root / "config" / "monitor.yaml").is_file())
        self.assert_error('print yaml_file_to_object("../outside.yaml")\n', "E721")
        self.assert_error('print yaml_validate_file("config/monitor.yaml")\n', "E720", RuntimeCapabilities.none(self.root))

    def test_xml_document_edit_search_escape_and_serialization(self):
        source = '''function:main
document = xml_document_parse("<server enabled=\\"true\\"><name>WEB01 &amp; DB</name><port>443</port></server>")
root = xml_root(document)
print xml_element_name(root)
print xml_get_attribute(root, "enabled")
name = xml_find(document, "/server/name")
print xml_element_text(name)
xml_set_element_text(name, "<ERROR>")
xml_set_attribute(root, "region", "東京 & east")
child = xml_create_element("status")
xml_set_element_text(child, "OK")
xml_add_child(root, child)
print length(xml_children(root))
print xml_element_text(xml_child(root, "status"))
print xml_document_to_text(document, indent = 2, declaration = true)
end_function:main
'''
        output = execute(source)[1]
        self.assertTrue(output.startswith("server\ntrue\nWEB01 & DB\n3\nOK\n"))
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', output)
        self.assertIn('region="東京 &amp; east"', output)
        self.assertIn("&lt;ERROR&gt;", output)

    def test_xml_namespace_and_simple_path_are_explicit(self):
        source = '''function:main
document = xml_document_parse("<soap:Envelope xmlns:soap=\\"urn:soap\\"><soap:Body><item>one</item><item>two</item></soap:Body></soap:Envelope>")
root = xml_root(document)
print xml_namespace_uri(root)
print xml_namespace_prefix(root)
xml_set_attribute(root, "id", "42", namespace_uri = "urn:meta")
print xml_get_attribute(root, "id", namespace_uri = "urn:meta")
items = xml_find_all(document, "/Envelope/Body/item")
print length(items)
print xml_element_text(items[1])
end_function:main
'''
        self.assertEqual(execute(source)[1], "urn:soap\nsoap\n42\n2\ntwo\n")
        self.assert_error('document = xml_document_parse("<a><b/></a>")\nprint xml_find(xml_root(document), "/a/b")\n', "E954")

    def test_xml_object_round_trip_preserves_namespaced_attributes(self):
        source = '''function:main
value = xml_to_object("<root xmlns:x=\\"urn:meta\\" x:id=\\"42\\"/>")
text = object_to_xml(value, declaration = false)
print contains(text, "urn:meta")
print contains(text, "42")
end_function:main
'''
        self.assertEqual(execute(source)[1], "true\ntrue\n")

    def test_xml_object_conversion_and_file_round_trip(self):
        source = '''function:main
value = xml_to_object("<monitor active=\\"yes\\"><name>監視</name></monitor>")
print value.name
print value.attributes.active
text = object_to_xml(value, indent = 2, declaration = false)
print text
object_to_xml_file("out/monitor.xml", value, indent = 2)
loaded = xml_file_to_object("out/monitor.xml")
print loaded.children[0].text
end_function:main
'''
        output = execute(source, capabilities=self.capability)[1]
        self.assertIn("monitor\nyes\n<monitor active=\"yes\">", output)
        self.assertTrue(output.endswith("監視\n"))

    def test_xml_security_parse_model_and_escape_errors_are_typed(self):
        cases = (
            ('print xml_document_parse("<!DOCTYPE x [<!ENTITY e SYSTEM \'file:///secret\'>]><x>&e;</x>")\n', "E952"),
            ('print xml_document_parse("<root><broken></root>")\n', "E950"),
            ('print xml_create_element("bad name")\n', "E951"),
            ('print xml_unescape("&unknown;")\n', "E955"),
        )
        for source, code in cases:
            with self.subTest(code=code): self.assert_error(source, code)
        diagnostic = self.assert_error('print xml_document_parse("<root>\\n<broken>\\n</root>")\n', "E950")
        self.assertIn("line 3", diagnostic.actual)
        source = '''function:main
try :parse
xml_document_parse("<broken>")
catch xml_error :parse
print "xml failed"
endtry:parse
end_function:main
'''
        self.assertEqual(execute(source)[1], "xml failed\n")

    def test_xml_remove_child_and_attribute_report_missing_values(self):
        source = '''function:main
document = xml_document_parse("<root key=\\"value\\"><child/></root>")
root = xml_root(document)
child = xml_child(root, "child")
xml_remove_child(root, child)
print length(xml_children(root))
xml_remove_attribute(root, "key")
print xml_get_attribute(root, "key")
end_function:main
'''
        self.assertEqual(execute(source)[1], "0\nnull\n")
        self.assert_error('document = xml_document_parse("<root/>")\nxml_remove_attribute(xml_root(document), "missing")\n', "E951")


if __name__ == "__main__": unittest.main()
