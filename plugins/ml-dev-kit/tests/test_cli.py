from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN, STANDARDS_OK, make_repo, commit, spec_text, write

BIN = PLUGIN / "bin" / "mdk"
RUN_DIR = "docs/features/accounts"
ONE_FEATURE = "01. sign-up — New users create an account.\n"
PASSING_TESTS = (
    "import unittest\n\n\n"
    "class SignUp(unittest.TestCase):\n"
    "    def test_01_B1(self):\n        pass\n\n"
    "    def test_01_B2(self):\n        pass\n"
)


def mdk(cwd, *args, stdin="", env=None):
    return subprocess.run(
        [sys.executable, str(BIN), *args], cwd=cwd, input=stdin, capture_output=True, text=True, env=env
    )


def event(root, **fields):
    return json.dumps({"cwd": str(root), **fields})


def edit_event(root, rel="src/a.py"):
    return event(root, tool_name="Edit", tool_input={"file_path": str(Path(root) / rel)})


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def ok(self, root, *args, stdin=""):
        done = mdk(root, *args, stdin=stdin)
        self.assertEqual(done.returncode, 0, f"mdk {' '.join(args)}\n{done.stdout}\n{done.stderr}")
        return done

    def approve(self, root):
        done = self.ok(root, "hook", "prompt", stdin=event(root, prompt="approve"))
        self.assertIn("recorded the human's Approval", done.stdout)

    def status(self, root):
        return json.loads(self.ok(root, "status").stdout)

    def bare_dir(self):
        path = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def started(self):
        root = make_repo(self.tmp)
        self.ok(root, "init", "accounts", "Let people sign up")
        return root

    def building(self):
        root = self.started()
        write(root, "STANDARDS.md", STANDARDS_OK)
        commit(root, "standards")
        self.ok(root, "await", "standards")
        self.approve(root)
        write(root, f"{RUN_DIR}/breakdown.md", ONE_FEATURE)
        self.ok(root, "await", "breakdown")
        self.approve(root)
        write(root, f"{RUN_DIR}/01-sign-up.md", spec_text("01"))
        self.ok(root, "await", "spec", "01")
        self.approve(root)
        commit(root, "spec 01")
        self.ok(root, "begin", "01")
        return root


class StatusTests(CliCase):
    def test_status_no_run(self):
        root = make_repo(self.tmp)
        done = mdk(root, "status")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(json.loads(done.stdout), {"active": False})

    def test_status_reports_the_active_run(self):
        status = self.status(self.started())
        self.assertEqual(
            sorted(status),
            sorted(["active", "slug", "goal", "branch", "stage", "awaiting", "current", "features", "escalation", "next"]),
        )
        self.assertEqual((status["active"], status["slug"], status["stage"]), (True, "accounts", "setup"))
        self.assertEqual((status["goal"], status["branch"]), ("Let people sign up", "mdk/accounts"))


class FlowTests(CliCase):
    def test_full_flow_through_cli(self):
        root = self.building()
        status = self.status(root)
        self.assertEqual((status["stage"], status["current"]), ("build", "01"))

        failed = mdk(root, "check", "01")
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout.splitlines()[0], "FAIL")

        write(root, "tests/test_a.py", PASSING_TESTS)
        passed = self.ok(root, "check", "01")
        self.assertEqual(passed.stdout.splitlines()[0], "PASS")
        self.assertIn("--- test output (tail) ---", passed.stdout)
        self.ok(root, "done", "01")
        self.assertEqual(self.status(root), {"active": False})

    def test_done_fails_without_passing_check_and_leaves_state_unchanged(self):
        root = self.building()
        before = (Path(root) / RUN_DIR / "state.json").read_text()
        failed = mdk(root, "done", "01")
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout.splitlines()[0], "FAIL")
        self.assertIn("- no test files match tests/**/*.py", failed.stdout)
        self.assertEqual((Path(root) / RUN_DIR / "state.json").read_text(), before)

    def test_done_needs_the_test_output_to_name_each_behaviour(self):
        # I4 through the CLI: unittest does not collect bare functions, so their names never reach the output.
        root = self.building()
        write(root, "tests/test_a.py", "def test_01_B1():\n    pass\n\n\ndef test_01_B2():\n    pass\n")
        failed = mdk(root, "done", "01")
        self.assertEqual(failed.returncode, 1)
        self.assertIn("- test output never names 01-B1 (did it run?)", failed.stdout)
        self.assertEqual(self.status(root)["stage"], "build")

    def test_await_breakdown_prints_the_features_it_read(self):
        # I6: the human approves the list mdk parsed, so they can see a Feature that did not make it.
        root = self.started()
        write(root, "STANDARDS.md", STANDARDS_OK)
        commit(root, "standards")
        self.ok(root, "await", "standards")
        self.approve(root)
        write(root, f"{RUN_DIR}/breakdown.md", "01. sign-up — New users.\n02. login — Users sign in.\n")
        done = self.ok(root, "await", "breakdown")
        self.assertEqual(done.stdout.splitlines()[:3], ["Features in build order:", "- 01. sign-up", "- 02. login"])

    def test_await_standards_lists_the_files_each_glob_matches(self):
        # I7/R19: Setup checks the globs with the matcher the Done check uses, from any folder.
        root = self.started()
        write(root, "tests/test_a.py", "x")
        write(root, "tests/unit/test_b.py", "x")
        write(root, "STANDARDS.md", "Test command: `python3 -m unittest -v`\nTest files: `tests/**/*.py`, `tests`, `tests/test_[ab].py`\n")
        (root / "sub").mkdir()
        for cwd in (root, root / "sub"):
            with self.subTest(cwd=cwd):
                lines = self.ok(cwd, "await", "standards").stdout.splitlines()
                self.assertEqual(lines[0], "Files the Done check searches for test names:")
                self.assertEqual(lines[1], "- `tests/**/*.py`: tests/test_a.py, tests/unit/test_b.py")
                for glob, line in zip(("tests", "tests/test_[ab].py"), lines[2:4]):
                    self.assertTrue(line.startswith(f"- `{glob}`: no files."), line)
                    self.assertIn("needs a wildcard", line)
                self.assertIn("approve", lines[-1])

    def test_await_standards_shortens_a_long_file_list(self):
        root = self.started()
        for n in range(13):
            write(root, f"tests/test_{n:02d}.py", "x")
        write(root, "STANDARDS.md", "Test command: `python3 -m unittest -v`\nTest files: `tests/*.py`\n")
        line = self.ok(root, "await", "standards").stdout.splitlines()[1]
        self.assertTrue(line.startswith("- `tests/*.py`: tests/test_00.py, "), line)
        self.assertTrue(line.endswith("tests/test_09.py and 3 more"), line)

    def test_escalate_joins_the_reason(self):
        root = self.building()
        self.ok(root, "escalate", "01", "cannot", "meet", "01-B2")
        status = self.status(root)
        self.assertEqual(status["stage"], "escalated")
        self.assertEqual(status["escalation"]["reason"], "cannot meet 01-B2")

    def test_await_spec_defaults_to_the_current_feature(self):
        root = self.building()
        self.ok(root, "escalate", "01", "needs", "a", "change")
        self.ok(root, "await", "spec")
        awaiting = self.status(root)["awaiting"]
        self.assertEqual((awaiting["kind"], awaiting["feature"]), ("spec", "01"))
        self.assertRegex(awaiting["sha256"], r"^[0-9a-f]{64}$")

    def test_await_spec_without_a_feature_exits_2(self):
        done = mdk(self.started(), "await", "spec")
        self.assertEqual(done.returncode, 2)
        self.assertTrue(done.stderr.startswith("mdk:"), done.stderr)

    def test_errors_exit_2_with_message(self):
        done = mdk(self.started(), "begin", "07")
        self.assertEqual(done.returncode, 2)
        self.assertTrue(done.stderr.startswith("mdk:"), done.stderr)

    def test_commands_that_need_a_run_say_how_to_start_one(self):
        done = mdk(make_repo(self.tmp), "await", "standards")
        self.assertEqual(done.returncode, 2)
        self.assertIn("mdk init", done.stderr)


class HookTests(CliCase):
    def test_hook_gate_outputs_deny_json(self):
        root = self.started()
        done = self.ok(root, "hook", "gate", stdin=edit_event(root))
        self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_hook_gate_prints_nothing_when_it_allows(self):
        root = self.started()
        done = self.ok(root, "hook", "gate", stdin=edit_event(root, "docs/adr/0001-queue.md"))
        self.assertEqual(done.stdout, "")

    def test_hook_gate_fails_closed_when_git_is_unusable_inside_a_run_project(self):
        # I1: without git the gate cannot see the Run, so it must block rather than wave the edit through.
        root = self.started()
        no_git = self.bare_dir()  # an empty PATH: the interpreter is called by absolute path
        for label, env in (
            ("git missing from PATH", dict(os.environ, PATH=str(no_git))),
            ("bad GIT_DIR", dict(os.environ, GIT_DIR=str(root / "nope"))),
        ):
            with self.subTest(label):
                done = mdk(root, "hook", "gate", stdin=edit_event(root), env=env)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertTrue(done.stderr.startswith("ml-dev-kit: hook error:"), done.stderr)

    def test_hook_gate_ignores_a_state_json_that_is_not_mdks(self):
        # M1: another tool's docs/features/<x>/state.json is not a Run.
        root = make_repo(self.tmp, {"docs/features/widgets/state.json": json.dumps({"enabled": True})})
        done = self.ok(root, "hook", "gate", stdin=edit_event(root))
        self.assertEqual(done.stdout, "")

    def test_hook_gate_fails_closed_on_bad_state(self):
        root = self.started()
        write(root, f"{RUN_DIR}/state.json", "{not json")
        done = mdk(root, "hook", "gate", stdin=edit_event(root))
        self.assertEqual(done.returncode, 2)
        self.assertTrue(done.stderr.startswith("ml-dev-kit: hook error:"), done.stderr)

    def test_hook_gate_fails_closed_from_a_subdirectory(self):
        root = self.started()
        write(root, f"{RUN_DIR}/state.json", "{not json")
        sub = root / "sub"
        sub.mkdir()
        stdin = event(sub, tool_name="Edit", tool_input={"file_path": "a.py"})
        self.assertEqual(mdk(self.bare_dir(), "hook", "gate", stdin=stdin).returncode, 2)

    def test_hook_gate_fails_closed_on_unparsable_stdin_inside_a_run_project(self):
        root = self.started()
        self.assertEqual(mdk(root, "hook", "gate", stdin="not json").returncode, 2)

    def test_hook_gate_fails_open_without_docs_features(self):
        root = make_repo(self.tmp)
        self.assertEqual(mdk(root, "hook", "gate", stdin="not json").returncode, 0)

    def test_hook_gate_fails_open_outside_a_repo(self):
        bare = self.bare_dir()
        self.assertEqual(mdk(bare, "hook", "gate", stdin=edit_event(bare)).returncode, 0)

    def test_hook_prompt_never_blocks_the_human(self):
        root = self.started()
        done = mdk(root, "hook", "prompt", stdin="not json")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "")
        self.assertIn("ml-dev-kit", done.stderr)

    def test_hook_prompt_survives_a_corrupt_run(self):
        root = self.started()
        write(root, f"{RUN_DIR}/state.json", "{not json")
        self.assertEqual(mdk(root, "hook", "prompt", stdin=event(root, prompt="approve")).returncode, 0)


class WiringTests(unittest.TestCase):
    def test_bin_is_executable(self):
        self.assertTrue(os.access(BIN, os.X_OK))
        self.assertTrue(BIN.read_text().startswith("#!/usr/bin/env python3\n"))

    def test_bin_runs_directly(self):
        done = subprocess.run([str(BIN), "--help"], capture_output=True, text=True, input="")
        self.assertEqual(done.returncode, 0)
        self.assertIn("mdk", done.stdout)

    def test_hooks_json_wires_both_events(self):
        hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertEqual(sorted(hooks), ["PreToolUse", "UserPromptSubmit"])
        for entries in hooks.values():
            for entry in entries:
                for hook in entry["hooks"]:
                    self.assertIn("bin/mdk", hook["command"])
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "Edit|Write|MultiEdit|NotebookEdit|Bash|apply_patch")


if __name__ == "__main__":
    unittest.main()
