import unittest

from separan.structure_insights import document_structure


SOURCE = '''function:main(value)
config = read_text(path)
if user.active :active_user
result = notify(user.name)
while retrying :retry_connection
attempt = reconnect(server)
endwhile:retry_connection
endif:active_user
end_function:main
'''


class StructureInsightsTests(unittest.TestCase):
    def test_hierarchy_ranges_and_parameters(self):
        report = document_structure(SOURCE, "app.sep")
        self.assertEqual(report["schema"], "separan.document-structure.v1")
        self.assertEqual(report["block_count"], 3)
        function = report["roots"][0]
        self.assertEqual((function["kind"], function["label"]), ("function", "main"))
        self.assertEqual(function["parameters"], ["value"])
        self.assertEqual((function["start_line"], function["end_line"]), (1, 9))
        self.assertEqual(function["children"][0]["children"][0]["label"], "retry_connection")

    def test_direct_summary_excludes_nested_named_blocks(self):
        function = document_structure(SOURCE)["roots"][0]
        self.assertEqual(function["reads"], ["path"])
        self.assertEqual(function["writes"], ["config"])
        self.assertEqual(function["calls"], ["read_text"])
        active = function["children"][0]
        self.assertEqual(active["reads"], ["user.active", "user.name"])
        self.assertEqual(active["writes"], ["result"])
        self.assertEqual(active["calls"], ["notify"])
        retry = active["children"][0]
        self.assertEqual(retry["reads"], ["retrying", "server"])
        self.assertEqual(retry["writes"], ["attempt"])
        self.assertEqual(retry["calls"], ["reconnect"])

    def test_unicode_label_identity_is_preserved(self):
        report = document_structure(SOURCE.replace("active_user", "利用者確認"))
        block = report["roots"][0]["children"][0]
        self.assertEqual(block["label"], "利用者確認")
        self.assertIn("if:利用者確認#1", block["path"])


if __name__ == "__main__": unittest.main()
