"""Codex sends apply_patch edits as one command, potentially touching many files."""
from __future__ import annotations

import json
import unittest

from helpers import PLUGIN, REPO, commit
from test_cli import mdk
from test_hooks import HookCase, decision, reason
from mdk.hooks import gate
from mdk.run import current_hash


def patch(cwd, *lines):
    return {
        "cwd": str(cwd), "hook_event_name": "PreToolUse", "turn_id": "codex-turn",
        "tool_name": "apply_patch",
        "tool_input": {"command": "\n".join(("*** Begin Patch", *lines, "*** End Patch"))},
    }


class CodexGateTests(HookCase):
    def test_source_add_update_and_delete_wait_for_approval(self):
        root, _ = self.spec_stage()
        for action in ("Add", "Update", "Delete"):
            with self.subTest(action=action):
                event = patch(root, f"*** {action} File: src/a.py")
                result = gate(event)
                self.assertIsNotNone(result)
                self.assertEqual(decision(result), "deny")
                self.assertIn("Waiting for the human", reason(result))

    def test_docs_are_allowed_but_one_source_file_blocks_a_whole_patch(self):
        root, _ = self.spec_stage()
        docs = ["*** Add File: docs/adr/0001.md", "+A decision.", "*** Update File: CONTEXT.md", "@@", "+A term."]
        self.assertIsNone(gate(patch(root, *docs)))
        result = gate(patch(root, *docs, "*** Add File: src/a.py", "+x = 1"))
        self.assertIsNotNone(result)
        self.assertEqual(decision(result), "deny")

    def test_move_checks_both_the_old_path_and_the_destination(self):
        root, _ = self.spec_stage()
        for old, new in (("CONTEXT.md", "src/a.py"), ("src/a.py", "CONTEXT.md")):
            with self.subTest(old=old, new=new):
                result = gate(patch(root, f"*** Update File: {old}", f"*** Move to: {new}", "@@", "-old", "+new"))
                self.assertIsNotNone(result)
                self.assertEqual(decision(result), "deny")

    def test_state_records_and_standards_stay_protected_during_build(self):
        root, _ = self.build_stage()
        for path in ("docs/features/accounts/state.json", "docs/features/accounts/Records.json", "standards.md"):
            for headers in ((f"*** Add File: {path}",), ("*** Update File: src/a.py", f"*** Move to: {path}")):
                with self.subTest(headers=headers):
                    result = gate(patch(root, *headers))
                    self.assertIsNotNone(result)
                    self.assertEqual(decision(result), "deny")

    def test_build_allows_source_until_the_approved_spec_changes(self):
        root, run = self.build_stage()
        event = patch(root, "*** Update File: src/a.py", "@@", "-old", "+new")
        self.assertIsNone(gate(event))
        path = run.spec_path("01")
        path.write_text(path.read_text() + "- A Deviation.\n")
        self.assertIsNone(gate(event))
        path.write_text(path.read_text().replace("do the thing", "do another thing"))
        result = gate(event)
        self.assertIsNotNone(result)
        self.assertIn("changed after its Approval", reason(result))

    def test_setup_allows_standards_and_requires_their_approval_for_source(self):
        root, run = self.setup_stage()
        self.assertIsNone(gate(patch(root, "*** Add File: STANDARDS.md", "+Rules.")))
        event = patch(root, "*** Add File: tests/test_a.py", "+test")
        self.assertIsNotNone(gate(event))
        self.approve_standards(root, run)
        self.assertIsNone(gate(event))

    def test_paths_resolve_from_cwd_and_follow_symlinks(self):
        root, _ = self.spec_stage()
        sub = root / "sub"
        sub.mkdir()
        (root / "notes.txt").symlink_to(root / "docs/features/accounts/state.json")
        for path in ("../src/a.py", str(root / "src/a.py"), "../notes.txt"):
            with self.subTest(path=path):
                self.assertIsNotNone(gate(patch(sub, f"*** Update File: {path}")))
        self.assertIsNone(gate(patch(sub, "*** Update File: ../CONTEXT.md", "@@", "+Term.")))
        self.assertIsNone(gate(patch(sub, "*** Add File: ../../outside.py", "+x")))

    def test_patch_content_that_looks_like_a_header_is_not_a_path(self):
        root, _ = self.spec_stage()
        self.assertIsNone(gate(patch(root, "*** Add File: CONTEXT.md", "+*** Add File: src/a.py")))

    def test_malformed_patches_deny_inside_a_run(self):
        root, _ = self.spec_stage()
        for command in (None, 1, "", "not a patch", "*** Begin Patch\n*** End Patch", "*** Begin Patch\n*** Add File: \n*** End Patch", "*** Begin Patch\n*** Move to: CONTEXT.md\n*** End Patch"):
            with self.subTest(command=command):
                event = patch(root)
                event["tool_input"]["command"] = command
                result = gate(event)
                self.assertIsNotNone(result)
                self.assertEqual(decision(result), "deny")
                self.assertIn("patch", reason(result).lower())

    def test_indented_file_directives_cannot_hide_later_source_paths(self):
        root, _ = self.spec_stage()
        for first in ("Add", "Delete"):
            for later in ("Add", "Update", "Delete"):
                with self.subTest(first=first, later=later):
                    lines = [f"*** {first} File: docs/adr/probe.md"]
                    if first == "Add":
                        lines.append("+A note.")
                    lines.append(f" *** {later} File: src/a.py")
                    if later == "Add":
                        lines.append("+unapproved = True")
                    elif later == "Update":
                        lines.extend(("@@", "-old", "+new"))
                    result = gate(patch(root, *lines))
                    self.assertIsNotNone(result)
                    self.assertEqual(decision(result), "deny")

    def test_leading_spaces_in_filenames_are_not_removed(self):
        root, _ = self.spec_stage()
        for action in ("Add", "Update", "Delete"):
            with self.subTest(action=action):
                self.assertIsNotNone(gate(patch(root, f"*** {action} File:  docs/adr/file.py")))
        self.assertIsNotNone(gate(patch(root, "*** Update File: CONTEXT.md", "*** Move to:  docs/adr/file.py", "@@", "+x")))

    def test_indented_marker_in_update_context_is_content(self):
        root, _ = self.spec_stage()
        self.assertIsNone(gate(patch(root, "*** Update File: CONTEXT.md", "@@", " *** Add File: src/a.py", "+text")))

    def test_end_of_file_cannot_hide_an_indented_next_file(self):
        root, _ = self.spec_stage()
        result = gate(patch(root, "*** Update File: CONTEXT.md", "@@", "+text", "*** End of File", " *** Add File: src/a.py", "+x"))
        self.assertIsNotNone(result)
        self.assertEqual(decision(result), "deny")

    def test_delete_and_move_check_the_project_symlink_entry(self):
        root, _ = self.spec_stage()
        (root / "STANDARDS.md").unlink()
        (root / "STANDARDS.md").symlink_to(self.tmp / "shared-standards.md")
        (root / "src").mkdir()
        (root / "src/a.py").symlink_to(self.tmp / "shared-source.py")
        for lines in (
            ("*** Delete File: STANDARDS.md",),
            ("*** Update File: src/a.py", "*** Move to: docs/adr/moved.py", "@@", "-old", "+new"),
        ):
            with self.subTest(lines=lines):
                result = gate(patch(root, *lines))
                self.assertIsNotNone(result)
                self.assertEqual(decision(result), "deny")

    def test_no_run_keeps_patch_hooks_inert(self):
        self.assertIsNone(gate(patch(self.tmp, "*** Add File: src/a.py", "+x")))
        self.assertIsNone(gate(patch(self.tmp)))

    def test_cli_receives_codex_events_and_uses_the_existing_approval_record(self):
        root, run = self.spec_stage()
        event = patch(root, "*** Update File: src/a.py", "@@", "+x")
        denied = mdk(root, "hook", "gate", stdin=json.dumps(event))
        self.assertEqual(denied.returncode, 0, denied.stderr)
        self.assertIn('"permissionDecision": "deny"', denied.stdout)
        approved = mdk(root, "hook", "prompt", stdin=json.dumps({
            "cwd": str(root), "hook_event_name": "UserPromptSubmit", "turn_id": "codex-turn", "prompt": "approve",
        }))
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertIn(current_hash(run, "spec", "01")[:12], approved.stdout)
        commit(root, "spec 01")
        begun = mdk(root, "begin", "01")
        self.assertEqual(begun.returncode, 0, begun.stderr)
        allowed = mdk(root, "hook", "gate", stdin=json.dumps(event))
        self.assertEqual((allowed.returncode, allowed.stdout), (0, ""), allowed.stderr)


class CodexPackagingTests(unittest.TestCase):
    def test_codex_marketplace_resolves_the_same_plugin(self):
        catalog = json.loads((REPO / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(catalog["name"], "ml-dev-kit")
        entry, = catalog["plugins"]
        self.assertEqual(entry["name"], "ml-dev-kit")
        self.assertEqual((REPO / entry["source"]["path"]).resolve(), PLUGIN.resolve())
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertTrue(entry["policy"]["authentication"])
        self.assertTrue(entry["category"])

    def test_codex_manifest_loads_shared_skills_and_hooks(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((manifest["name"], manifest["version"]), (claude["name"], claude["version"]))
        self.assertEqual((PLUGIN / manifest["skills"]).resolve(), (PLUGIN / "skills").resolve())
        self.assertEqual((PLUGIN / manifest["hooks"]).resolve(), (PLUGIN / "hooks/hooks.json").resolve())
        hooks = json.loads((PLUGIN / manifest["hooks"]).read_text())["hooks"]
        self.assertIn("apply_patch", hooks["PreToolUse"][0]["matcher"])
        self.assertIn("UserPromptSubmit", hooks)


if __name__ == "__main__":
    unittest.main()
