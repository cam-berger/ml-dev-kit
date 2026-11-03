from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import build_ready_repo, commit, spec_text, write
from mdk.check import CheckResult, check_feature
from mdk.run import current_hash

NAMES = "print('test_01_B1 ... ok'); print('test_01_B2 ... ok')"
GREEN = f"python3 -c \"{NAMES}\""
RED = f"python3 -c \"import sys; {NAMES}; print('boom'); sys.exit(1)\""
UNNAMED = ["test output never names 01-B1 (did it run?)", "test output never names 01-B2 (did it run?)"]
UNITTEST = f"\"{sys.executable}\" -m unittest discover -s tests"
CASES = (
    "import unittest\n\n\nclass SignUp(unittest.TestCase):\n"
    "    def test_01_B1(self):\n        pass\n\n    def test_01_b2_lowercase(self):\n        pass\n"
)
SLOW = "python3 -c \"import time; time.sleep(5)\""
BOTH_IDS = "def test_01_B1(): pass\ndef test_01_B2(): pass\n"


class CheckFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def ready(self, command: str = GREEN, tests: str | None = BOTH_IDS):
        root, run = build_ready_repo(self.tmp, command)
        if tests is not None:
            write(root, "tests/test_x.py", tests)
        return root, run

    def test_passes_when_ids_covered_and_suite_green(self):
        _, run = self.ready()
        r = check_feature(run, "01")
        self.assertIsInstance(r, CheckResult)
        self.assertTrue(r.passed, r.problems)
        self.assertEqual(r.problems, [])
        self.assertIn("ok", r.output_tail)

    def test_fails_missing_behaviour_test(self):
        _, run = self.ready(tests="def test_01_B1(): pass\n")
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertEqual(r.problems, ["no test names 01-B2"])

    def test_ids_outside_test_files_do_not_count(self):
        root, run = self.ready(tests="def test_01_B1(): pass\n")
        write(root, "notes/cover.py", BOTH_IDS)
        self.assertEqual(check_feature(run, "01").problems, ["no test names 01-B2"])

    def test_committed_nested_test_file_counts(self):
        root, run = self.ready(tests=None)
        write(root, "tests/unit/test_x.py", BOTH_IDS)
        commit(root, "tests")
        r = check_feature(run, "01")
        self.assertTrue(r.passed, r.problems)

    def test_gitignored_test_file_does_not_count(self):
        root, run = self.ready(tests=None)
        write(root, ".gitignore", "tests/generated/\n")
        write(root, "tests/generated/test_x.py", BOTH_IDS)
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertIn("no test files match tests/**/*.py", r.problems)

    def test_tracked_but_deleted_test_file_is_skipped(self):
        root, run = self.ready(tests="def test_01_B1(): pass\n")
        write(root, "tests/test_gone.py", "def test_01_B2(): pass\n")
        commit(root, "tests")
        (root / "tests/test_gone.py").unlink()
        self.assertEqual(check_feature(run, "01").problems, ["no test names 01-B2"])

    def test_fails_no_test_files(self):
        _, run = self.ready(tests=None)
        r = check_feature(run, "01")
        self.assertTrue(any("no test files match tests/**/*.py" in p for p in r.problems), r.problems)
        self.assertFalse(r.passed)

    def test_fails_red_suite(self):
        _, run = self.ready(RED)
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertEqual(r.problems, ["test command failed (exit 1)"])
        self.assertIn("boom", r.output_tail)

    def test_output_tail_is_last_40_lines(self):
        _, run = self.ready(f"python3 -c \"{NAMES}; [print(n) for n in range(100)]\"")
        lines = check_feature(run, "01").output_tail.split("\n")
        self.assertEqual((lines[0], lines[-1], len(lines)), ("60", "99", 40))

    def test_fails_when_test_output_never_names_a_behaviour(self):
        # I4: a green suite that never ran the Feature's tests proves nothing.
        _, run = self.ready("python3 -c \"print('Ran 0 tests'); print('OK')\"")
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertEqual(r.problems, UNNAMED)

    def test_zero_tests_collected_fails(self):
        # The reviewer's probe: unittest does not collect bare functions. Before Python 3.12 it then exits 0;
        # `; exit 0` pins that on every version.
        tests = "def test_01_B1(): assert False\ndef test_01_B2(): assert False\n"
        _, run = self.ready(UNITTEST + " -v; exit 0", tests=tests)
        r = check_feature(run, "01")
        self.assertIn("Ran 0 tests", r.output_tail)
        self.assertEqual(r.problems, UNNAMED)

    def test_a_quiet_test_command_fails_because_it_names_no_test(self):
        _, run = self.ready(UNITTEST, tests=CASES)
        self.assertEqual(check_feature(run, "01").problems, UNNAMED)

    def test_passes_when_a_verbose_runner_names_each_test(self):
        _, run = self.ready(UNITTEST + " -v", tests=CASES)
        r = check_feature(run, "01")
        self.assertTrue(r.passed, r.problems)

    def test_test_names_are_read_from_the_whole_output_not_the_tail(self):
        _, run = self.ready(f"python3 -c \"{NAMES}; [print(n) for n in range(100)]\"")
        r = check_feature(run, "01")
        self.assertTrue(r.passed, r.problems)
        self.assertNotIn("test_01_B1", r.output_tail)

    def test_fails_when_the_spec_lists_no_behaviour_ids(self):
        # I5: with no IDs there is nothing for a test to cover, so Done would prove nothing.
        root, run = self.ready()
        run.spec_path("01").write_text(spec_text("01", behaviours=()), encoding="utf-8")
        records = json.loads((run.dir / "records.json").read_text(encoding="utf-8"))
        records["approvals"].append({"kind": "spec", "feature": "01", "sha256": current_hash(run, "spec", "01"), "at": "x"})
        (run.dir / "records.json").write_text(json.dumps(records), encoding="utf-8")
        self.assertEqual(check_feature(run, "01").problems, ["Spec 01 lists no Behaviour IDs, so no test can show it was built"])

    def test_test_command_gets_no_stdin(self):
        # The hook's or the shell's stdin must not reach the suite: a test that reads it would hang or vary.
        reads = "import sys; data = sys.stdin.read(); " + NAMES + "; sys.exit(3 if data else 0)"
        _, run = self.ready(f"python3 -c \"{reads}\"")
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b"not for the suite")
        os.close(write_fd)
        saved = os.dup(0)
        try:
            os.dup2(read_fd, 0)
            r = check_feature(run, "01")
        finally:
            os.dup2(saved, 0)
            os.close(saved)
            os.close(read_fd)
        self.assertTrue(r.passed, r.problems)

    def test_fails_when_spec_changed_after_approval(self):
        _, run = self.ready()
        path = run.spec_path("01")
        path.write_text(path.read_text().replace("Users can do", "Users can also do"), encoding="utf-8")
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertEqual(r.problems, ["Spec 01 has no current Approval"])

    def test_deviations_do_not_void_the_approval(self):
        _, run = self.ready()
        path = run.spec_path("01")
        path.write_text(spec_text("01") + "- Used a queue instead of a thread.\n", encoding="utf-8")
        self.assertTrue(check_feature(run, "01").passed)

    def test_timeout_reported(self):
        _, run = self.ready(SLOW)
        r = check_feature(run, "01", timeout=1)
        self.assertEqual(r.problems, ["test command timed out after 1s"])
        self.assertFalse(r.passed)

    def test_timeout_kills_the_whole_command_not_just_the_shell(self):
        root, run = self.ready("sleep 30 & echo $! > child.pid; wait")
        self.addCleanup(self.reap, root / "child.pid")
        r = check_feature(run, "01", timeout=1)
        self.assertEqual(r.problems, ["test command timed out after 1s"])
        pid = int((root / "child.pid").read_text())
        deadline = time.monotonic() + 2
        while self.alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.alive(pid), "the test command's child outlived the timeout")

    def test_timeout_keeps_partial_output(self):
        _, run = self.ready("echo partial; sleep 30 && echo never")
        r = check_feature(run, "01", timeout=1)
        self.assertIn("partial", r.output_tail)
        self.assertNotIn("never", r.output_tail)

    @staticmethod
    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def reap(self, pid_file: Path):
        if pid_file.exists() and self.alive(int(pid_file.read_text())):
            os.kill(int(pid_file.read_text()), 9)

    def test_missing_runner_reported(self):
        _, run = self.ready("definitely-not-a-command-xyz")
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertEqual(r.problems, ["test command failed (exit 127)", *UNNAMED])

    def test_collects_every_problem(self):
        _, run = self.ready("python3 -c \"import sys; sys.exit(1)\"", tests=None)
        path = run.spec_path("01")
        path.write_text(path.read_text().replace("Users can do", "Users can also do"), encoding="utf-8")
        self.assertEqual(check_feature(run, "01").problems, [
            "Spec 01 has no current Approval",
            "no test files match tests/**/*.py",
            "no test names 01-B1",
            "no test names 01-B2",
            "test command failed (exit 1)",
            *UNNAMED,
        ])

    def test_missing_standards_is_a_problem_not_a_crash(self):
        root, run = self.ready()
        (root / "STANDARDS.md").unlink()
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertTrue(any("STANDARDS.md" in p for p in r.problems), r.problems)

    def test_unparseable_standards_reports_the_doc_error(self):
        root, run = self.ready()
        write(root, "STANDARDS.md", "# Standards\n\nNo commands here.\n")
        r = check_feature(run, "01")
        self.assertFalse(r.passed)
        self.assertTrue(any("Test command" in p for p in r.problems), r.problems)


if __name__ == "__main__":
    unittest.main()
