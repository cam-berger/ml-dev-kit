from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import BREAKDOWN_OK, STANDARDS_OK, commit, make_repo, spec_text, write
from mdk.docs import DocError, text_hash
from mdk.run import (
    RunError,
    active_run,
    begin_build,
    current_hash,
    escalate,
    init_run,
    is_approved,
    mark_done,
    next_action,
    project_root,
    record_approval,
    request_approval,
)

SLUG = "accounts"
GOAL = "Let people sign up and log in"


class RunCase(unittest.TestCase):
    """A repo with STANDARDS.md at self.root, plus builders for each point in a Run's life."""

    def setUp(self):
        self.root = self.repo({"STANDARDS.md": STANDARDS_OK})

    def repo(self, files=None) -> Path:
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return make_repo(Path(tmp), files)

    def git(self, *args: str, root=None) -> str:
        done = subprocess.run(["git", *args], cwd=root or self.root, check=True, capture_output=True, text=True)
        return done.stdout.strip()

    def saved(self, run) -> dict:
        return json.loads((run.dir / "state.json").read_text(encoding="utf-8"))

    def records(self, run) -> dict:
        return json.loads((run.dir / "records.json").read_text(encoding="utf-8"))

    def started(self):
        return init_run(self.root, SLUG, GOAL)

    def with_breakdown_approved(self):
        run = self.started()
        write(self.root, f"docs/features/{SLUG}/breakdown.md", BREAKDOWN_OK)
        request_approval(run, "breakdown")
        record_approval(run)
        return run

    def approve_spec(self, run, fid="01") -> Path:
        path = run.spec_path(fid)
        path.write_text(spec_text(fid), encoding="utf-8")
        request_approval(run, "spec", fid)
        record_approval(run)
        return path

    def building(self):
        run = self.with_breakdown_approved()
        self.approve_spec(run)
        commit(self.root, "spec 01")
        begin_build(run, "01")
        return run


class InitTests(RunCase):
    def test_init_creates_branch_and_state(self):
        root = self.repo()
        run = init_run(root, SLUG, GOAL)
        self.assertEqual(run.stage, "setup")
        self.assertEqual(self.git("branch", "--show-current", root=root), "mdk/accounts")
        self.assertEqual(active_run(root).slug, "accounts")
        self.assertEqual(
            self.saved(run),
            {
                "goal": GOAL,
                "slug": SLUG,
                "branch": "mdk/accounts",
                "stage": "setup",
                "awaiting": None,
                "current": None,
                "features": [],
                "escalation": None,
            },
        )
        self.assertEqual(self.records(run), {"approvals": [], "done": []})

    def test_init_stage_breakdown_when_standards_exist(self):
        self.assertEqual(self.started().stage, "breakdown")

    def test_state_files_are_indented_json_with_trailing_newline_and_no_temp_residue(self):
        run = self.started()
        for name in ("state.json", "records.json"):
            text = (run.dir / name).read_text(encoding="utf-8")
            self.assertEqual(text, json.dumps(json.loads(text), indent=2) + "\n")
        self.assertEqual(sorted(p.name for p in run.dir.iterdir()), ["records.json", "state.json"])

    def test_init_refuses_dirty_tree(self):
        write(self.root, "scratch.txt", "unsaved work")
        with self.assertRaises(RunError):
            self.started()
        self.assertEqual(self.git("branch", "--list", "mdk/*"), "")

    def test_init_refuses_second_run(self):
        self.started()
        commit(self.root, "run files")
        with self.assertRaisesRegex(RunError, SLUG):
            init_run(self.root, "payments", "Take payments")

    def test_init_rejects_bad_slug(self):
        for slug in ("Bad Slug", "", "-x", "a--b", "x_y"):
            with self.subTest(slug=slug), self.assertRaises(RunError):
                init_run(self.root, slug, GOAL)

    def test_init_refuses_existing_directory(self):
        (self.root / "docs" / "features" / SLUG).mkdir(parents=True)
        with self.assertRaises(RunError):
            self.started()
        self.assertEqual(self.git("branch", "--list", "mdk/*"), "")


class DiscoveryTests(RunCase):
    def test_project_root_requires_git(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with self.assertRaises(RunError):
            project_root(tmp)
        with self.assertRaises(RunError):
            project_root(tmp / "missing")

    def test_project_root_from_subdirectory(self):
        sub = self.root / "a" / "b"
        sub.mkdir(parents=True)
        self.assertEqual(project_root(sub).resolve(), self.root.resolve())

    def test_active_run_ignores_files_and_dirs_without_state(self):
        write(self.root, "docs/features/notes.md", "loose file")
        (self.root / "docs" / "features" / "scratch").mkdir()
        self.assertIsNone(active_run(self.root))
        commit(self.root, "strays")
        self.assertEqual(self.started().slug, SLUG)
        self.assertEqual(active_run(self.root).slug, SLUG)

    def test_active_run_refuses_two_active_runs(self):
        run = self.started()
        other = self.root / "docs" / "features" / "other"
        other.mkdir()
        for name in ("state.json", "records.json"):
            shutil.copy(run.dir / name, other / name)
        with self.assertRaisesRegex(RunError, "accounts.*other"):
            active_run(self.root)

    def test_active_run_ignores_a_state_json_without_records(self):
        # M1: every Run directory holds records.json from init on, so a lone state.json belongs to something else.
        write(self.root, "docs/features/widgets/state.json", json.dumps({"enabled": True}))
        self.assertIsNone(active_run(self.root))

    def test_active_run_reports_state_without_mdks_shape(self):
        for state in ({"enabled": True}, [], "x"):
            with self.subTest(state=state):
                write(self.root, "docs/features/widgets/state.json", json.dumps(state))
                write(self.root, "docs/features/widgets/records.json", json.dumps({"approvals": [], "done": []}))
                with self.assertRaisesRegex(RunError, "widgets/state.json is not an mdk Run file"):
                    active_run(self.root)

    def test_unreadable_records_are_a_run_error(self):
        run = self.started()
        write(self.root, f"docs/features/{SLUG}/breakdown.md", BREAKDOWN_OK)
        (run.dir / "records.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(RunError, "records.json is not an mdk Run file"):
            is_approved(run, "breakdown")

    def test_active_run_reports_unreadable_state(self):
        run = self.started()
        (run.dir / "state.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(RunError):
            active_run(self.root)


class ApprovalTests(RunCase):
    def test_await_standards_needs_setup_stage_and_valid_file(self):
        with self.assertRaises(RunError):  # STANDARDS.md already existed, so the Run began at breakdown
            request_approval(self.started(), "standards")

        root = self.repo()
        run = init_run(root, SLUG, GOAL)
        with self.assertRaises(RunError):  # missing
            request_approval(run, "standards")
        write(root, "STANDARDS.md", "# Standards\n")
        with self.assertRaises(DocError):  # does not parse
            request_approval(run, "standards")

    def test_await_breakdown_requires_standards_approval_in_setup(self):
        root = self.repo()
        run = init_run(root, SLUG, GOAL)
        write(root, "STANDARDS.md", STANDARDS_OK)
        write(root, f"docs/features/{SLUG}/breakdown.md", BREAKDOWN_OK)
        with self.assertRaises(RunError):
            request_approval(run, "breakdown")
        request_approval(run, "standards")
        record_approval(run)
        request_approval(run, "breakdown")
        self.assertEqual(run.stage, "breakdown")
        self.assertEqual(run.awaiting, {"kind": "breakdown", "feature": None, "sha256": current_hash(run, "breakdown")})
        self.assertEqual(
            run.features,
            [
                {"id": "01", "slug": "sign-up", "status": "pending", "base": None},
                {"id": "02", "slug": "login", "status": "pending", "base": None},
            ],
        )
        self.assertEqual(self.saved(run), run.state)

    def test_await_breakdown_rejects_a_breakdown_that_does_not_parse(self):
        run = self.started()
        write(self.root, f"docs/features/{SLUG}/breakdown.md", "just some prose\n")
        with self.assertRaises(DocError):
            request_approval(run, "breakdown")
        self.assertEqual(run.features, [])

    def test_await_breakdown_refuses_once_a_feature_has_started(self):
        run = self.with_breakdown_approved()
        run.feature("01")["status"] = "done"
        with self.assertRaises(RunError):
            request_approval(run, "breakdown")

    def test_standards_approval_tracks_file_hash(self):
        root = self.repo()
        run = init_run(root, SLUG, GOAL)
        write(root, "STANDARDS.md", STANDARDS_OK)
        self.assertFalse(is_approved(run, "standards"))
        request_approval(run, "standards")
        record = record_approval(run)
        self.assertEqual(record["sha256"], current_hash(run, "standards"))
        self.assertTrue(is_approved(run, "standards"))
        write(root, "STANDARDS.md", STANDARDS_OK + "\nOne more rule.\n")
        self.assertFalse(is_approved(run, "standards"))

    def test_record_approval_stores_kind_feature_hash_and_utc_time(self):
        run = self.with_breakdown_approved()
        self.approve_spec(run)
        spec_record = self.records(run)["approvals"][-1]
        self.assertEqual(set(spec_record), {"kind", "feature", "sha256", "at"})
        self.assertEqual((spec_record["kind"], spec_record["feature"]), ("spec", "01"))
        self.assertTrue(spec_record["at"].endswith("+00:00"))
        self.assertIsNone(self.records(run)["approvals"][0]["feature"])
        self.assertIsNone(run.awaiting)
        self.assertEqual(self.saved(run), run.state)

    def test_record_approval_refuses_a_document_changed_since_await(self):
        # I5: the human must approve exactly the text mdk checked, not an edit made after `mdk await`.
        root = self.repo()
        run = init_run(root, SLUG, GOAL)
        write(root, "STANDARDS.md", STANDARDS_OK)
        request_approval(run, "standards")
        write(root, "STANDARDS.md", "# Standards\n\nNothing mdk can read.\n")
        self.assertIsNone(record_approval(run))
        self.assertEqual(self.records(run)["approvals"], [])
        self.assertEqual(run.awaiting["kind"], "standards")
        write(root, "STANDARDS.md", STANDARDS_OK)
        request_approval(run, "standards")
        self.assertIsNotNone(record_approval(run))

        run = self.with_breakdown_approved()
        path = run.spec_path("01")
        path.write_text(spec_text("01"), encoding="utf-8")
        request_approval(run, "spec", "01")
        path.write_text(spec_text("01").replace("- **01-B1**", "- B1").replace("- **01-B2**", "- B2"), encoding="utf-8")
        before = self.records(run)
        self.assertIsNone(record_approval(run))
        self.assertEqual(self.records(run), before)
        self.assertFalse(is_approved(run, "spec", "01"))
        commit(self.root, "spec")
        with self.assertRaises(RunError):
            begin_build(run, "01")

    def test_record_approval_allows_deviations_edits_since_await(self):
        run = self.with_breakdown_approved()
        path = run.spec_path("01")
        path.write_text(spec_text("01"), encoding="utf-8")
        request_approval(run, "spec", "01")
        path.write_text(spec_text("01") + "- note\n", encoding="utf-8")
        self.assertIsNotNone(record_approval(run))

    def test_record_approval_without_awaiting_returns_none(self):
        run = self.started()
        self.assertIsNone(record_approval(run))
        self.assertEqual(self.records(run)["approvals"], [])

    def test_is_approved_is_false_when_the_document_is_missing(self):
        run = self.with_breakdown_approved()
        path = self.approve_spec(run)
        self.assertTrue(is_approved(run, "spec", "01"))
        path.unlink()
        self.assertFalse(is_approved(run, "spec", "01"))
        self.assertIsNone(current_hash(run, "spec", "01"))

    def test_latest_approval_wins(self):
        run = self.with_breakdown_approved()
        breakdown = run.dir / "breakdown.md"
        breakdown.write_text(BREAKDOWN_OK + "03. logout — Users sign out.\n", encoding="utf-8")
        request_approval(run, "breakdown")
        record_approval(run)
        breakdown.write_text(BREAKDOWN_OK, encoding="utf-8")
        self.assertFalse(is_approved(run, "breakdown"))

    def test_spec_approval_survives_deviations_but_not_body_edits(self):
        run = self.with_breakdown_approved()
        path = self.approve_spec(run)
        path.write_text(path.read_text(encoding="utf-8") + "- 01-B1: used a helper.\n", encoding="utf-8")
        self.assertTrue(is_approved(run, "spec", "01"))
        path.write_text(path.read_text(encoding="utf-8").replace("hand", "machine"), encoding="utf-8")
        self.assertFalse(is_approved(run, "spec", "01"))

    def test_await_spec_requires_approved_breakdown(self):
        run = self.started()
        write(self.root, f"docs/features/{SLUG}/breakdown.md", BREAKDOWN_OK)
        request_approval(run, "breakdown")
        run.spec_path("01").write_text(spec_text("01"), encoding="utf-8")
        with self.assertRaisesRegex(RunError, "breakdown"):
            request_approval(run, "spec", "01")

    def test_await_spec_lists_spec_problems(self):
        run = self.with_breakdown_approved()
        run.spec_path("01").write_text(
            spec_text("01").replace("## Out of scope", "## Later"), encoding="utf-8"
        )
        with self.assertRaisesRegex(RunError, "Out of scope"):
            request_approval(run, "spec", "01")
        self.assertIsNone(run.awaiting)

    def test_await_spec_needs_the_spec_file_and_a_feature_id(self):
        run = self.with_breakdown_approved()
        with self.assertRaises(RunError):
            request_approval(run, "spec", "01")
        with self.assertRaises(RunError):
            request_approval(run, "spec")
        with self.assertRaises(RunError):
            request_approval(run, "spec", "07")

    def test_await_spec_sets_stage_current_and_awaiting(self):
        run = self.with_breakdown_approved()
        run.spec_path("01").write_text(spec_text("01"), encoding="utf-8")
        request_approval(run, "spec", "01")
        self.assertEqual((run.stage, run.current), ("spec", "01"))
        self.assertEqual(run.awaiting, {"kind": "spec", "feature": "01", "sha256": current_hash(run, "spec", "01")})
        self.assertEqual(self.saved(run), run.state)

    def test_await_spec_refuses_while_another_feature_builds(self):
        run = self.building()
        run.spec_path("02").write_text(spec_text("02"), encoding="utf-8")
        with self.assertRaisesRegex(RunError, "01"):
            request_approval(run, "spec", "02")

    def test_await_spec_follows_breakdown_order(self):
        run = self.with_breakdown_approved()
        run.spec_path("02").write_text(spec_text("02"), encoding="utf-8")
        with self.assertRaisesRegex(RunError, "01"):  # 01 has not even started
            request_approval(run, "spec", "02")
        self.assertIsNone(run.awaiting)
        self.assertIsNone(run.current)

    def test_await_spec_cannot_step_around_an_escalated_feature(self):
        run = self.building()
        escalate(run, "01", "scope change")
        run.spec_path("02").write_text(spec_text("02"), encoding="utf-8")
        with self.assertRaisesRegex(RunError, "01"):
            request_approval(run, "spec", "02")
        self.assertEqual(run.stage, "escalated")
        self.assertEqual(run.state["escalation"]["feature"], "01")
        self.assertIsNone(run.awaiting)

    def test_await_spec_refuses_a_feature_that_is_building_or_done(self):
        run = self.building()
        with self.assertRaises(RunError):
            request_approval(run, "spec", "01")
        mark_done(run, "01")
        with self.assertRaises(RunError):
            request_approval(run, "spec", "01")

    def test_unknown_kind_is_rejected(self):
        run = self.started()
        with self.assertRaises(RunError):
            request_approval(run, "design")
        with self.assertRaises(RunError):
            is_approved(run, "design")


class BuildTests(RunCase):
    def test_begin_requires_approved_spec(self):
        run = self.with_breakdown_approved()
        run.spec_path("01").write_text(spec_text("01"), encoding="utf-8")
        commit(self.root, "spec")
        with self.assertRaises(RunError):
            begin_build(run, "01")
        request_approval(run, "spec", "01")  # asked, not yet approved
        with self.assertRaises(RunError):
            begin_build(run, "01")

    def test_begin_requires_committed_spec(self):
        run = self.with_breakdown_approved()
        self.approve_spec(run)
        with self.assertRaises(RunError):
            begin_build(run, "01")
        self.assertEqual(run.feature("01")["status"], "pending")

    def test_begin_records_base_and_stage_build(self):
        run = self.with_breakdown_approved()
        self.approve_spec(run)
        commit(self.root, "spec")
        begin_build(run, "01")
        self.assertEqual(run.feature("01")["base"], self.git("rev-parse", "HEAD"))
        self.assertEqual(run.feature("01")["status"], "building")
        self.assertEqual((run.stage, run.current), ("build", "01"))
        self.assertIsNone(run.state["escalation"])
        self.assertEqual(self.saved(run), run.state)

    def test_begin_refuses_a_feature_already_building(self):
        run = self.building()
        with self.assertRaises(RunError):
            begin_build(run, "01")

    def test_escalate_requires_building(self):
        run = self.with_breakdown_approved()
        with self.assertRaises(RunError):
            escalate(run, "01", "too early")

    def test_escalate_records_reason(self):
        run = self.building()
        escalate(run, "01", "needs a payments provider")
        self.assertEqual(run.feature("01")["status"], "escalated")
        self.assertEqual(run.stage, "escalated")
        escalation = run.state["escalation"]
        self.assertEqual(
            (escalation["feature"], escalation["reason"]), ("01", "needs a payments provider")
        )
        self.assertTrue(escalation["at"].endswith("+00:00"))
        self.assertEqual(self.saved(run), run.state)

    def test_escalate_then_reapprove_keeps_base(self):
        run = self.building()
        base = run.feature("01")["base"]
        escalate(run, "01", "scope change")
        spec = run.spec_path("01")
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("Anything not listed", "Payments; anything not listed"),
            encoding="utf-8",
        )
        request_approval(run, "spec", "01")
        self.assertEqual((run.stage, run.feature("01")["status"]), ("spec", "escalated"))
        record_approval(run)
        commit(self.root, "revised spec")
        self.assertNotEqual(self.git("rev-parse", "HEAD"), base)
        begin_build(run, "01")
        self.assertEqual(run.feature("01")["base"], base)
        self.assertEqual(run.stage, "build")
        self.assertEqual(run.feature("01")["status"], "building")
        self.assertIsNone(run.state["escalation"])

    def test_begin_after_escalation_needs_a_fresh_approval_from_the_human(self):
        run = self.building()
        escalate(run, "01", "scope change")
        with self.assertRaises(RunError):  # the old Approval still matches the unchanged Spec
            begin_build(run, "01")
        request_approval(run, "spec", "01")
        with self.assertRaises(RunError):  # asked, but the human has not answered
            begin_build(run, "01")
        record_approval(run)
        begin_build(run, "01")
        self.assertEqual(run.stage, "build")

    def test_mark_done_requires_build_stage(self):
        run = self.with_breakdown_approved()
        with self.assertRaises(RunError):
            mark_done(run, "01")

    def test_mark_done_requires_the_current_feature(self):
        run = self.building()
        with self.assertRaises(RunError):
            mark_done(run, "02")
        self.assertEqual(self.records(run)["done"], [])

    def test_mark_done_refuses_a_spec_body_changed_after_approval(self):
        run = self.building()
        spec = run.spec_path("01")
        spec.write_text(
            spec.read_text(encoding="utf-8").replace("Anything not", "Everything but"), encoding="utf-8"
        )
        with self.assertRaisesRegex(RunError, "mdk escalate 01"):
            mark_done(run, "01")
        self.assertEqual(self.records(run)["done"], [])
        self.assertEqual((run.stage, run.feature("01")["status"]), ("build", "building"))

    def test_mark_done_accepts_deviations_added_during_build(self):
        run = self.building()
        spec = run.spec_path("01")
        spec.write_text(spec.read_text(encoding="utf-8") + "- 01-B1: used a helper.\n", encoding="utf-8")
        mark_done(run, "01")
        self.assertEqual(run.feature("01")["status"], "done")
        self.assertEqual(self.records(run)["done"][0]["sha256"], text_hash(spec.read_text(encoding="utf-8")))

    def test_mark_done_ends_the_run_only_when_every_feature_is_done(self):
        run = self.building()
        run.feature("02")["status"] = "escalated"  # unreachable through the API; belt and braces
        mark_done(run, "01")
        self.assertEqual((run.stage, run.current), ("spec", "02"))
        self.assertIsNotNone(active_run(self.root))

    def test_mark_done_advances_to_next_feature(self):
        run = self.building()
        mark_done(run, "01")
        self.assertEqual((run.current, run.stage), ("02", "spec"))
        self.assertEqual(run.feature("01")["status"], "done")
        self.assertEqual(self.saved(run), run.state)

        self.approve_spec(run, "02")
        commit(self.root, "spec 02")
        begin_build(run, "02")
        mark_done(run, "02")
        self.assertEqual(run.stage, "done")
        self.assertIsNone(run.current)
        self.assertIsNone(active_run(self.root))
        done = self.records(run)["done"]
        self.assertEqual([d["feature"] for d in done], ["01", "02"])
        self.assertEqual(set(done[0]), {"feature", "sha256", "at"})


class NextActionTests(RunCase):
    def test_next_action_mentions_approve_when_awaiting(self):
        root = self.repo()
        run = init_run(root, SLUG, GOAL)
        write(root, "STANDARDS.md", STANDARDS_OK)
        request_approval(run, "standards")
        self.assertIn("approve", next_action(run))
        record_approval(run)
        write(root, f"docs/features/{SLUG}/breakdown.md", BREAKDOWN_OK)
        request_approval(run, "breakdown")
        self.assertIn("approve", next_action(run))
        record_approval(run)
        run.spec_path("01").write_text(spec_text("01"), encoding="utf-8")
        request_approval(run, "spec", "01")
        text = next_action(run)
        self.assertIn("approve", text)
        self.assertIn("01", text)

    def test_next_action_before_standards_and_breakdown(self):
        run = init_run(self.repo(), SLUG, GOAL)
        self.assertIn("STANDARDS.md", next_action(run))
        self.assertIn("breakdown", next_action(self.started()))

    def test_next_action_names_the_feature_through_the_stages(self):
        run = self.with_breakdown_approved()
        self.assertIn("01", next_action(run))
        self.approve_spec(run)
        text = next_action(run)
        self.assertIn("01", text)
        self.assertIn("begin", text)
        commit(self.root, "spec")
        begin_build(run, "01")
        self.assertIn("01", next_action(run))
        escalate(run, "01", "needs a payments provider")
        text = next_action(run)
        self.assertIn("01", text)
        self.assertIn("needs a payments provider", text)

    def test_next_action_after_done(self):
        run = self.building()
        mark_done(run, "01")
        self.assertIn("02", next_action(run))
        self.approve_spec(run, "02")
        commit(self.root, "spec 02")
        begin_build(run, "02")
        mark_done(run, "02")
        self.assertEqual(next_action(run), "Run complete.")


if __name__ == "__main__":
    unittest.main()
