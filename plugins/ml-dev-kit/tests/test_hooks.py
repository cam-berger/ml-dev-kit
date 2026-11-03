from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import BREAKDOWN_OK, STANDARDS_OK, build_ready_repo, make_repo, spec_text, write
from mdk.hooks import gate, on_prompt
from mdk.run import current_hash, escalate, init_run, is_approved, record_approval, request_approval

SLUG = "accounts"
RUN_DIR = f"docs/features/{SLUG}"
FILE_KEY = {"NotebookEdit": "notebook_path"}


def edit(root, rel, tool="Edit"):
    return in_cwd(root, str(Path(root) / rel), tool)


def in_cwd(cwd, path, tool="Edit"):
    return {"cwd": str(cwd), "tool_name": tool, "tool_input": {FILE_KEY.get(tool, "file_path"): path}}


def bash(root, command):
    return {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": command}}


def prompt(root, text):
    return {"cwd": str(root), "prompt": text}


def decision(result):
    return result["hookSpecificOutput"]["permissionDecision"]


def reason(result):
    return result["hookSpecificOutput"]["permissionDecisionReason"]


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def fresh(self):
        return Path(tempfile.mkdtemp(dir=self.tmp))

    def setup_stage(self):
        root = make_repo(self.fresh())
        return root, init_run(root, SLUG, "Let people sign up")

    def approve_standards(self, root, run):
        write(root, "STANDARDS.md", STANDARDS_OK)
        request_approval(run, "standards")
        record_approval(run)

    def spec_stage(self):
        root = make_repo(self.fresh(), {"STANDARDS.md": STANDARDS_OK})
        run = init_run(root, SLUG, "Let people sign up")
        write(root, f"{RUN_DIR}/breakdown.md", BREAKDOWN_OK)
        request_approval(run, "breakdown")
        record_approval(run)
        run.spec_path("01").write_text(spec_text("01"), encoding="utf-8")
        request_approval(run, "spec", "01")
        return root, run

    def build_stage(self):
        return build_ready_repo(self.fresh(), "python3 -c pass")

    def records(self, run):
        return json.loads((run.dir / "records.json").read_text(encoding="utf-8"))


class GateTests(HookCase):
    def test_gate_allows_outside_git(self):
        self.assertIsNone(gate(edit(self.tmp, "src/a.py")))
        self.assertIsNone(gate(bash(self.tmp, "cat docs/features/x/records.json")))

    def test_gate_allows_when_no_run(self):
        root = make_repo(self.fresh(), {"STANDARDS.md": STANDARDS_OK})
        self.assertIsNone(gate(edit(root, "src/a.py")))
        self.assertIsNone(gate(edit(root, "STANDARDS.md")))
        self.assertIsNone(gate(bash(root, "cat records.json")))

    def test_gate_denies_source_edit_before_spec_approval(self):
        root, run = self.spec_stage()
        result = gate(edit(root, "src/a.py"))
        self.assertEqual(decision(result), "deny")
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertTrue(reason(result).startswith("ml-dev-kit: "))
        self.assertIn("Waiting for the human to approve the Spec for feature 01", reason(result))

    def test_gate_allows_docs_and_context_during_spec(self):
        root, _ = self.spec_stage()
        for rel in (f"{RUN_DIR}/01-sign-up.md", f"{RUN_DIR}/noticed.md", "docs/adr/0001.md", "CONTEXT.md"):
            with self.subTest(rel=rel):
                self.assertIsNone(gate(edit(root, rel)))

    def test_gate_denies_state_and_records_edits(self):
        root, _ = self.spec_stage()
        for rel in (f"{RUN_DIR}/state.json", f"{RUN_DIR}/records.json"):
            for tool in ("Edit", "Write", "MultiEdit"):
                with self.subTest(stage="spec", rel=rel, tool=tool):
                    result = gate(edit(root, rel, tool))
                    self.assertEqual(decision(result), "deny")
                    self.assertIn("mdk", reason(result))

    def test_gate_denies_state_and_records_edits_in_build(self):
        root, _ = self.build_stage()
        for rel in (f"{RUN_DIR}/state.json", f"{RUN_DIR}/records.json"):
            with self.subTest(rel=rel):
                self.assertEqual(decision(gate(edit(root, rel))), "deny")

    def test_gate_denies_bash_mentioning_records(self):
        root, _ = self.build_stage()
        for command in (
            "cat docs/features/accounts/records.json",
            "echo '{}' > records.json",
            "sed -i s/a/b/ docs/features/accounts/state.json",
            "python3 -c \"open('docs/features/accounts/state.json','w')\"",
        ):
            with self.subTest(command=command):
                result = gate(bash(root, command))
                self.assertEqual(decision(result), "deny")
                self.assertTrue(reason(result).startswith("ml-dev-kit: "))
                self.assertIn("mdk", reason(result))

    def test_gate_allows_other_bash(self):
        root, _ = self.spec_stage()
        for command in ("ls", "git status", "python3 -m unittest", "cat state.json", "mdk status", "cat docs/features/accounts/breakdown.md"):
            with self.subTest(command=command):
                self.assertIsNone(gate(bash(root, command)))

    def test_gate_allows_source_edit_in_build(self):
        root, _ = self.build_stage()
        self.assertIsNone(gate(edit(root, "src/a.py")))
        self.assertIsNone(gate(edit(root, "tests/test_a.py", "MultiEdit")))

    def test_gate_denies_after_spec_body_changed(self):
        root, run = self.build_stage()
        path = run.spec_path("01")
        path.write_text(path.read_text(encoding="utf-8").replace("do the thing", "do another thing"), encoding="utf-8")
        result = gate(edit(root, "src/a.py"))
        self.assertEqual(decision(result), "deny")
        self.assertIn("Build feature 01", reason(result))

    def test_gate_allows_after_deviations_changed(self):
        root, run = self.build_stage()
        path = run.spec_path("01")
        path.write_text(path.read_text(encoding="utf-8") + "- Used a different seam.\n", encoding="utf-8")
        self.assertIsNone(gate(edit(root, "src/a.py")))

    def test_gate_standards_only_in_setup(self):
        root, _ = self.setup_stage()
        self.assertIsNone(gate(edit(root, "STANDARDS.md")))
        for name, stage in (("spec", self.spec_stage), ("build", self.build_stage)):
            with self.subTest(stage=name):
                result = gate(edit(stage()[0], "STANDARDS.md"))
                self.assertEqual(decision(result), "deny")
                self.assertIn("human-owned", reason(result))
                self.assertIn("ask the human", reason(result))

    def test_gate_setup_writes_need_standards_approval(self):
        root, run = self.setup_stage()
        self.assertEqual(decision(gate(edit(root, "src/a.py"))), "deny")
        self.assertIsNone(gate(edit(root, f"{RUN_DIR}/breakdown.md")))
        self.assertIsNone(gate(edit(root, "CONTEXT.md")))
        self.approve_standards(root, run)
        self.assertIsNone(gate(edit(root, "src/a.py")))
        write(root, "STANDARDS.md", STANDARDS_OK + "\nMore.\n")
        self.assertEqual(decision(gate(edit(root, "src/a.py"))), "deny")

    def test_gate_denies_in_escalated(self):
        root, run = self.build_stage()
        escalate(run, "01", "the Spec cannot be met")
        result = gate(edit(root, "src/a.py"))
        self.assertEqual(decision(result), "deny")
        self.assertIn("escalated", reason(result))
        self.assertIsNone(gate(edit(root, f"{RUN_DIR}/01-sign-up.md")))

    def test_gate_covers_every_edit_tool(self):
        root, _ = self.spec_stage()
        for tool, rel in (("Edit", "a.py"), ("Write", "a.py"), ("MultiEdit", "a.py"), ("NotebookEdit", "nb/a.ipynb")):
            with self.subTest(tool=tool):
                self.assertEqual(decision(gate(edit(root, rel, tool))), "deny")

    def test_gate_allows_paths_outside_repo(self):
        root, _ = self.spec_stage()
        self.assertIsNone(gate(in_cwd(root, "/tmp/elsewhere.py")))
        self.assertIsNone(gate(in_cwd(root, f"{root}-sibling/a.py")))

    def test_gate_resolves_relative_path_against_cwd(self):
        root, _ = self.spec_stage()
        (root / "sub").mkdir()
        sub = root / "sub"
        self.assertEqual(decision(gate(in_cwd(root, "src/a.py"))), "deny")
        self.assertEqual(decision(gate(in_cwd(sub, "../src/a.py"))), "deny")
        self.assertEqual(decision(gate(in_cwd(sub, f"../{RUN_DIR}/state.json"))), "deny")
        self.assertEqual(decision(gate(in_cwd(root, "docs/../src/a.py"))), "deny")
        self.assertIsNone(gate(in_cwd(sub, "../CONTEXT.md")))
        self.assertIsNone(gate(in_cwd(sub, "../../elsewhere.py")))

    def test_gate_sees_through_symlinks(self):
        root, _ = self.spec_stage()
        link = self.tmp / "link"
        os.symlink(root, link)
        self.assertEqual(decision(gate(edit(link, "src/a.py"))), "deny")
        os.symlink(root / RUN_DIR / "state.json", root / "notes.txt")
        self.assertEqual(decision(gate(edit(root, "notes.txt"))), "deny")

    def test_gate_ignores_other_tools_and_partial_events(self):
        root, _ = self.spec_stage()
        for event in (
            {},
            {"cwd": str(root)},
            {"cwd": str(root), "tool_name": "Read", "tool_input": {"file_path": str(root / "src/a.py")}},
            {"cwd": str(root), "tool_name": "Edit", "tool_input": {}},
            {"cwd": str(root), "tool_name": "Edit"},
            {"cwd": str(root), "tool_name": "NotebookEdit", "tool_input": {"file_path": str(root / "a.py")}},
            {"cwd": str(root), "tool_name": "Bash", "tool_input": {}},
            {"tool_name": "Edit", "tool_input": {"file_path": str(root / "src/a.py")}},
        ):
            with self.subTest(event=event):
                self.assertIsNone(gate(event))


class PromptTests(HookCase):
    def test_prompt_records_approval_on_exact_token(self):
        root, run = self.spec_stage()
        for text in ("approve", "Approved!", "  APPROVE.  "):
            with self.subTest(text=text):
                request_approval(run, "spec", "01")
                before = len(self.records(run)["approvals"])
                result = on_prompt(prompt(root, text))
                self.assertIn("recorded", result["hookSpecificOutput"]["additionalContext"])
                self.assertEqual(len(self.records(run)["approvals"]), before + 1)
                self.assertTrue(is_approved(run, "spec", "01"))

    def test_prompt_reports_what_was_recorded(self):
        root, run = self.spec_stage()
        sha = current_hash(run, "spec", "01")[:12]
        self.assertEqual(on_prompt(prompt(root, "approve")), {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"ml-dev-kit: recorded the human's Approval of spec 01 (sha256 {sha})",
            }
        })

    def test_prompt_omits_missing_feature(self):
        root, run = self.setup_stage()
        write(root, "STANDARDS.md", STANDARDS_OK)
        request_approval(run, "standards")
        sha = current_hash(run, "standards")[:12]
        result = on_prompt(prompt(root, "approve"))
        self.assertEqual(
            result["hookSpecificOutput"]["additionalContext"],
            f"ml-dev-kit: recorded the human's Approval of standards (sha256 {sha})",
        )

    def test_prompt_ignores_other_text(self):
        root, run = self.spec_stage()
        saved = ((run.dir / "records.json").read_text(), (run.dir / "state.json").read_text())
        for text in ("don't approve yet", "approve but change X", "looks good", "approve!!", "approve\nbut change X", "", "disapprove"):
            with self.subTest(text=text):
                self.assertIsNone(on_prompt(prompt(root, text)))
        self.assertEqual(saved, ((run.dir / "records.json").read_text(), (run.dir / "state.json").read_text()))
        self.assertEqual(self.records(run)["approvals"][-1]["kind"], "breakdown")

    def test_prompt_ignores_when_nothing_awaiting(self):
        root, run = self.spec_stage()
        record_approval(run)
        before = (run.dir / "records.json").read_text()
        self.assertIsNone(on_prompt(prompt(root, "approve")))
        self.assertEqual((run.dir / "records.json").read_text(), before)

    def test_prompt_ignores_when_no_run_or_no_repo(self):
        root = make_repo(self.fresh(), {"STANDARDS.md": STANDARDS_OK})
        self.assertIsNone(on_prompt(prompt(root, "approve")))
        self.assertIsNone(on_prompt(prompt(self.tmp, "approve")))

    def test_prompt_ignores_partial_events(self):
        root, run = self.spec_stage()
        for event in ({}, {"cwd": str(root)}, {"prompt": "approve"}):
            with self.subTest(event=event):
                self.assertIsNone(on_prompt(event))
        self.assertIsNotNone(run.awaiting)


if __name__ == "__main__":
    unittest.main()
