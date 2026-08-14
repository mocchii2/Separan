import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from separan.structural import (
    ScopeResolutionError, inspect_source, main, structural_diff, verify_scopes,
    verify_tag_paths, verify_tag_scope,
)


BEFORE = """function:main
print "outside"
if true :active_user
print "hello"
endif:active_user
end_function:main
"""


class StructuralTests(unittest.TestCase):
    def snapshot(self, source, name):
        return inspect_source(source, name)

    def test_inspection_emits_hierarchical_machine_identities(self):
        snapshot = self.snapshot(BEFORE, "before.sep")
        self.assertEqual([item.path for item in snapshot.blocks], [
            "root", "function:main#1", "function:main#1/if:active_user#1",
        ])
        data = snapshot.to_dict()
        self.assertEqual(data["schema"], "separan.structure.v2")
        self.assertEqual(data["blocks"][2]["parent_id"], "root/function:main#1")
        self.assertEqual(data["blocks"][2]["start_line"], 3)

    def test_comments_whitespace_and_indentation_are_not_structural_changes(self):
        after = """##note
ignored
##note
  function:main
    print "outside"
    if true :active_user
      print "hello"
    endif:active_user
  end_function:main
"""
        report = structural_diff(self.snapshot(BEFORE, "a"), self.snapshot(after, "b"))
        self.assertEqual(report["changes"], [])
        self.assertEqual(report["summary"]["unchanged"], 3)

    def test_nested_edit_only_marks_the_nested_block(self):
        after = BEFORE.replace('print "hello"', 'print "hello again"')
        report = structural_diff(self.snapshot(BEFORE, "a"), self.snapshot(after, "b"))
        self.assertEqual([(item["status"], item["path"]) for item in report["changes"]], [
            ("modified", "function:main#1/if:active_user#1"),
        ])

    def test_scope_verification_accepts_change_inside_scope(self):
        after = BEFORE.replace('print "hello"', 'print "welcome"')
        report = verify_scopes(self.snapshot(BEFORE, "a"), self.snapshot(after, "b"), ["active_user"])
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"], {"allowed_changes": 1, "violations": 0})

    def test_scope_verification_rejects_change_outside_scope(self):
        after = BEFORE.replace('print "outside"', 'print "changed"')
        report = verify_scopes(self.snapshot(BEFORE, "a"), self.snapshot(after, "b"), [":active_user"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["violations"][0]["path"], "function:main#1")

    def test_scope_boundary_cannot_be_removed_or_renamed(self):
        after = BEFORE.replace("active_user", "enabled_user")
        report = verify_scopes(self.snapshot(BEFORE, "a"), self.snapshot(after, "b"), ["active_user"])
        self.assertFalse(report["passed"])
        self.assertTrue(any(item["status"] == "boundary_removed" for item in report["violations"]))

    def test_new_nested_structure_is_allowed_inside_scope(self):
        addition = """while false :never
print "no"
endwhile:never
"""
        after = BEFORE.replace('print "hello"\n', 'print "hello"\n' + addition)
        report = verify_scopes(self.snapshot(BEFORE, "a"), self.snapshot(after, "b"), ["active_user"])
        self.assertTrue(report["passed"])
        self.assertTrue(any(item["status"] == "added" for item in report["allowed_changes"]))

    def test_ambiguous_label_requires_a_path(self):
        source = """function:first
if true :same
endif:same
end_function:first
function:second
if true :same
endif:same
end_function:second
"""
        snapshot = self.snapshot(source, "a")
        with self.assertRaisesRegex(ScopeResolutionError, "S402"):
            verify_scopes(snapshot, snapshot, ["same"])
        report = verify_scopes(snapshot, snapshot, ["function:first/if:same"])
        self.assertTrue(report["passed"])

    def test_unknown_scope_is_a_specific_error(self):
        snapshot = self.snapshot(BEFORE, "a")
        with self.assertRaisesRegex(ScopeResolutionError, "S401"):
            verify_scopes(snapshot, snapshot, ["missing"])

    def test_cli_verify_has_review_friendly_exit_codes_and_json(self):
        snapshots = [self.snapshot(BEFORE, "before.sep"), self.snapshot(BEFORE.replace('print "outside"', 'print "changed"'), "after.sep")]
        output = io.StringIO()
        with patch("separan.structural.inspect_file", side_effect=snapshots), contextlib.redirect_stdout(output):
            status = main(["verify", "before.sep", "after.sep", "--allow", "active_user", "--json"])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(output.getvalue())["passed"])

    def test_semantic_tag_scope_resolves_all_tagged_functions(self):
        before = '''function:notify
@notification
print "one"
end_function:notify
function:archive
@notification
print "two"
end_function:archive
function:config
print "fixed"
end_function:config
'''
        after = before.replace('print "one"', 'print "changed"')
        report = verify_tag_scope(self.snapshot(before, "a"), self.snapshot(after, "b"), "notification")
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["resolved_functions"], 2)
        rejected = verify_tag_scope(self.snapshot(before, "a"), self.snapshot(before.replace('print "fixed"', 'print "changed"'), "b"), "@notification")
        self.assertFalse(rejected["passed"])

    def test_tag_metadata_is_exposed_in_snapshot(self):
        snapshot = self.snapshot('function:notify\n@notification\n@通知\nend_function:notify\n', "tag.sep")
        self.assertEqual(snapshot.blocks[1].tags, ("notification", "通知"))

    def test_workspace_tag_inspection_and_verification(self):
        fixtures = Path(__file__).parent / "fixtures"
        before, after, outside = fixtures / "tag_before", fixtures / "tag_after", fixtures / "tag_after_outside"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["inspect", str(before), "--tag", "notification", "--json"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["function_count"], 1)
        self.assertTrue(verify_tag_paths(before, after, "notification")["passed"])
        self.assertFalse(verify_tag_paths(before, outside, "notification")["passed"])


if __name__ == "__main__":
    unittest.main()
