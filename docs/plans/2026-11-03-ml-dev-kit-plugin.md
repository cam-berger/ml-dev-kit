# ml-dev-kit Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `ml-dev-kit` Claude Code plugin. One command, `/ml-dev-kit:feature <goal>`, runs a Goal through human-approved Specs, then test-first Build and Review, with Approval and Done enforced by code rather than prompt text.

**Architecture:** The plugin has three parts:

- **A stdlib-only Python package `mdk`.** It lives in `plugins/ml-dev-kit/lib/mdk/` and owns every Run file. It parses docs, moves the Run through its Stages, runs the Done check, and implements the hooks.
- **A CLI, `bin/mdk`.** The orchestrator calls it to change Run state; the model never edits the state files directly. The same CLI is the entry point for the hooks.
- **Prose files on top.** One user-invoked orchestrator skill, three subagents, and a few templates.

The repo root is a single-plugin marketplace.

**Tech Stack:** Python ≥3.9, standard library only (`unittest`, `subprocess`, `hashlib`, `json`, `re`), and git. Claude Code plugin format: skills, agents, `hooks/hooks.json`, `bin/`.

**Spec:** `docs/specs/2026-11-03-feature-workflow-plugin-design.md`. Domain terms are in `CONTEXT.md`.

## Global Constraints

- Python ≥3.9, stdlib only. Every module starts with `from __future__ import annotations`. No `match` statements, and no runtime `X | Y` unions.
- Plugin name: `ml-dev-kit`. Orchestrator skill: `feature`, invoked as `/ml-dev-kit:feature`. Marketplace name: `ml-dev-kit`.
- Run files go in `docs/features/<goal-slug>/`: `state.json`, `records.json`, `breakdown.md`, `NN-<feature-slug>.md`, `noticed.md`. Only `mdk` writes `state.json` and `records.json`.
- Per-project files go at the project root: `STANDARDS.md` (human-owned) and `CONTEXT.md`.
- The approval token is a whole message of `approve` or `approved`, case-insensitive, with optional surrounding whitespace and one trailing `.` or `!`. Nothing else counts.
- Each Run's branch is `mdk/<goal-slug>`. The plugin commits locally and never pushes.
- Slugs match `^[a-z0-9]+(-[a-z0-9]+)*$`. Feature IDs are two digits, `01`, `02`, and so on. Behaviour IDs are `<NN>-B<k>`, such as `02-B3`.
- The fix loop is capped at 3 rounds, then becomes an Escalation.
- Hooks fail closed (exit 2) only when `docs/features/` exists in the project. Otherwise they fail open (exit 0).
- Attribution in `NOTICE`:
  - mattpocock/skills, MIT, "Copyright (c) 2026 Matt Pocock";
  - obra/superpowers, MIT, "Copyright (c) 2025 Jesse Vincent".
- Docs and prompts stay short: say why, not what. Follow the anti-goals in the spec (section 4).
- Test command for this repo, run from the repo root: `python3 -m unittest discover -s plugins/ml-dev-kit/tests -v`

## Review Focus

1. **Plugin enabled where no Run exists.** This covers a non-git folder, a repo without `docs/features/`, or a finished Run. Hooks must never block or print anything. Pinned in Task 5: `test_gate_allows_outside_git` and `test_gate_allows_when_no_run`.
2. **The Spec body edited after Approval**, for example the agent "fixing" the Spec mid-Build. Code edits must be blocked until it is re-approved. Edits only to `## Deviations` must not trigger this. Pinned in Task 5: `test_gate_denies_after_spec_body_changed` and `test_gate_allows_after_deviations_changed`.
3. **Near-miss approvals** such as "approve but change X", "don't approve yet", "looks good", or "approve" when nothing is waiting. None of these may record anything. Pinned in Task 5: `test_prompt_ignores_other_text` and `test_prompt_ignores_when_nothing_awaiting`.
4. **Edit paths that are relative or outside the repo.** Relative paths resolve against the event's `cwd`. Paths outside the repo are allowed. Pinned in Task 5: `test_gate_resolves_relative_path_against_cwd` and `test_gate_allows_paths_outside_repo`.
5. **A test command that hangs or doesn't exist.** The Done check reports a failure; it doesn't crash or hang. Pinned in Task 4: `test_timeout_reported` and `test_missing_runner_reported`.

---

## File Structure

```
.claude-plugin/marketplace.json            # repo is a one-plugin marketplace
README.md                                  # install + use + develop (short)
NOTICE                                     # MIT attributions
.gitignore
plugins/ml-dev-kit/
  .claude-plugin/plugin.json
  bin/mdk                                  # CLI launcher (executable)
  lib/mdk/__init__.py
  lib/mdk/docs.py                          # pure parsing + hashing of Run docs
  lib/mdk/run.py                           # Run discovery, state transitions, Approval records
  lib/mdk/check.py                         # mechanical Done check
  lib/mdk/hooks.py                         # PreToolUse gate + UserPromptSubmit approval
  lib/mdk/cli.py                           # argparse wiring, exit codes
  hooks/hooks.json
  agents/implementer.md  agents/reviewer.md  agents/spec-checker.md
  skills/feature/SKILL.md                  # orchestrator
  skills/feature/references/{setup,spec,build}.md
  skills/feature/templates/{spec,breakdown,standards}.md
  tests/helpers.py  tests/test_*.py
```

---

### Task 1: Marketplace scaffold and test harness

**Files:**
- Create: `.claude-plugin/marketplace.json`, `plugins/ml-dev-kit/.claude-plugin/plugin.json`, `.gitignore`, `plugins/ml-dev-kit/lib/mdk/__init__.py` (empty)
- Test: `plugins/ml-dev-kit/tests/helpers.py`, `plugins/ml-dev-kit/tests/test_manifest.py`

**Interfaces:**
- Produces, in `tests/helpers.py`:
  - On import, it puts `lib/` on `sys.path`.
  - Constants: `PLUGIN: Path` (the plugin root) and `REPO: Path`.
  - Helpers:
    - `make_repo(tmp: Path, files: dict[str, str] | None = None) -> Path`: runs `git init -b main`, sets a local user name and email, writes the files, commits "init", and returns the root.
    - `write(root: Path, rel: str, text: str) -> Path`
    - `commit(root: Path, msg: str) -> None`: `git add -A` then commit.
  - Fixture texts:
    - `STANDARDS_OK`: contains the lines ``Test command: `python3 -m unittest discover -s tests` `` and ``Test files: `tests/**/*.py` ``.
    - `BREAKDOWN_OK`: two features, `01. sign-up — New users create an account.` and `02. login — Users sign in.`
    - `spec_text(fid: str = "01", behaviours: tuple[str, ...] = ("B1", "B2")) -> str`: a valid Spec with sections Intent, Behaviours (`- **01-B1** — ...`), Interface and seams, Out of scope, Deviations, in that order.

- [ ] **Step 1: Write the failing test** in `tests/test_manifest.py`.

```python
def test_marketplace_lists_plugin(self):
    m = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
    self.assertEqual(m["name"], "ml-dev-kit")
    self.assertEqual(m["plugins"][0]["source"], "./plugins/ml-dev-kit")
def test_plugin_manifest(self):
    p = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    self.assertEqual(p["name"], "ml-dev-kit"); self.assertIn("version", p)
def test_make_repo_commits(self):  # helper sanity
    root = make_repo(Path(self.tmp), {"a.txt": "x"})
    out = subprocess.run(["git", "log", "--oneline"], cwd=root, capture_output=True, text=True).stdout
    self.assertIn("init", out)
```

- [ ] **Step 2:** Run `python3 -m unittest discover -s plugins/ml-dev-kit/tests -v`. Expected: FAIL (manifest files missing).
- [ ] **Step 3: Create the manifests.**
  - `marketplace.json`: `name` `ml-dev-kit`, `owner.name` `cam-berger`, and one plugin entry with `name`, `source`, `description` and `version` `0.1.0`.
  - `plugin.json`: `name`, `version` `0.1.0`, and a one-sentence `description`.
  - `.gitignore`: `__pycache__/`.
- [ ] **Step 4:** Run the suite. Expected: PASS. Then run `claude plugin validate .` and `claude plugin validate plugins/ml-dev-kit`. Expected: no errors.
- [ ] **Step 5:** Commit: `chore: scaffold ml-dev-kit marketplace and test harness`

---

### Task 2: `docs.py` — parse and hash Run documents

**Files:**
- Create: `plugins/ml-dev-kit/lib/mdk/docs.py`
- Test: `plugins/ml-dev-kit/tests/test_docs.py`

**Interfaces:**
- Produces:
  - `SPEC_SECTIONS = ("Intent", "Behaviours", "Interface and seams", "Out of scope", "Deviations")`
  - `class DocError(ValueError)`
  - `spec_problems(text: str, feature_id: str) -> list[str]`: returns one human-readable line per problem, or `[]`.
  - `behaviour_ids(text: str) -> list[str]`: the unique IDs inside `## Behaviours`, in order of appearance.
  - `spec_body_hash(text: str) -> str` and `text_hash(text: str) -> str`: sha256 hex.
  - `@dataclass(frozen=True) PlannedFeature(id: str, slug: str, summary: str)`
  - `parse_breakdown(text: str) -> list[PlannedFeature]`
  - `@dataclass(frozen=True) Standards(test_command: str, test_globs: tuple[str, ...])`
  - `parse_standards(text: str) -> Standards`
  - `glob_to_regex(pattern: str) -> re.Pattern[str]`
  - `mentions_id(text: str, behaviour_id: str) -> bool`

- [ ] **Step 1: Write the failing tests.**

```python
def test_behaviour_ids_in_order(self): self.assertEqual(behaviour_ids(spec_text()), ["01-B1", "01-B2"])
def test_behaviour_ids_ignore_other_sections(self):
    t = spec_text().replace("## Intent\n", "## Intent\nSee 01-B9.\n")
    self.assertEqual(behaviour_ids(t), ["01-B1", "01-B2"])
def test_spec_problems_ok(self): self.assertEqual(spec_problems(spec_text(), "01"), [])
def test_spec_problems_missing_section(self):
    self.assertTrue(any("Out of scope" in p for p in spec_problems(spec_text().replace("## Out of scope", "## Later"), "01")))
def test_spec_problems_deviations_not_last(self):  # move "## Deviations" above "## Out of scope"
    self.assertTrue(any("Deviations" in p for p in spec_problems(moved, "01")))
def test_spec_problems_wrong_prefix(self): self.assertTrue(any("02-B1" in p for p in spec_problems(spec_text("02"), "01")))
def test_spec_problems_no_behaviours(self): self.assertTrue(spec_problems(spec_text(behaviours=()), "01"))
def test_body_hash_ignores_deviations(self):
    self.assertEqual(spec_body_hash(spec_text()), spec_body_hash(spec_text() + "\n- 01-B1: returns 423 for locked accounts\n"))
def test_body_hash_sees_body_changes(self):
    self.assertNotEqual(spec_body_hash(spec_text()), spec_body_hash(spec_text().replace("## Intent\n", "## Intent\nNew.\n")))
def test_body_hash_ignores_line_endings(self): self.assertEqual(spec_body_hash(spec_text()), spec_body_hash(spec_text().replace("\n", "\r\n")))
def test_parse_breakdown(self):
    self.assertEqual(parse_breakdown(BREAKDOWN_OK)[1], PlannedFeature("02", "login", "Users sign in."))
def test_parse_breakdown_accepts_hyphen(self): self.assertEqual(len(parse_breakdown(BREAKDOWN_OK.replace(" — ", " - "))), 2)
def test_parse_breakdown_rejects_gap(self):  # 01 then 03
    with self.assertRaises(DocError): parse_breakdown("01. a — x\n03. b — y\n")
def test_parse_breakdown_rejects_empty(self):
    with self.assertRaises(DocError): parse_breakdown("# Breakdown\n")
def test_parse_standards(self):
    self.assertEqual(parse_standards(STANDARDS_OK), Standards("python3 -m unittest discover -s tests", ("tests/**/*.py",)))
def test_parse_standards_missing_command(self):
    with self.assertRaisesRegex(DocError, "Test command"): parse_standards("Test files: `t/*.py`\n")
def test_glob_to_regex(self):
    r = glob_to_regex("tests/**/*.py")
    self.assertTrue(r.fullmatch("tests/a.py")); self.assertTrue(r.fullmatch("tests/x/y/a.py")); self.assertFalse(r.fullmatch("src/a.py"))
    self.assertTrue(glob_to_regex("**/*.test.ts").fullmatch("a.test.ts")); self.assertFalse(glob_to_regex("*.py").fullmatch("d/a.py"))
def test_mentions_id(self):
    self.assertTrue(mentions_id("def test_01_B2_x():", "01-B2")); self.assertTrue(mentions_id("# 01-B2", "01-B2"))
    self.assertFalse(mentions_id("01-B21", "01-B2")); self.assertFalse(mentions_id("101-B2", "01-B2"))
```

- [ ] **Step 2:** Run the suite. Expected: FAIL (`ModuleNotFoundError: mdk.docs`).
- [ ] **Step 3: Implement `docs.py`.** Pinned rules:
  - Sections are `## <name>` lines. `spec_problems` checks:
    - all five sections are present, in order, with Deviations last;
    - there is at least one Behaviour ID;
    - every ID's prefix equals `feature_id`.
  - Behaviour ID regex: `(?<![0-9A-Za-z])(\d{2})-B(\d+)(?![0-9])`.
  - `spec_body_hash`:
    - converts `\r\n` to `\n`;
    - keeps only the text before the first line equal to `## Deviations`;
    - strips trailing whitespace from each line and from the end;
    - returns the sha256.
  - `text_hash` uses the same normalisation but hashes the whole text.
  - Breakdown lines match `^(\d{2})\. ([a-z0-9]+(?:-[a-z0-9]+)*) [—-] (.+)$`. Other lines are ignored. IDs must run `01..n` with no gaps, and slugs must be unique.
  - Standards lines:
    - ``^Test command:\s*`([^`]+)`\s*$``
    - ``^Test files:\s*(.+)$``, where the globs are the backticked items, comma-separated.
    - A missing line raises `DocError` naming it.
  - `glob_to_regex`: `**/` → `(?:.*/)?`, `**` → `.*`, `*` → `[^/]*`, `?` → `[^/]`. Everything else goes through `re.escape`.
  - `mentions_id("NN-Bk")` matches `NN[-_]Bk` using the same lookarounds as the ID regex.
- [ ] **Step 4:** Run the suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: parse and hash Run documents`

---

### Task 3: `run.py` — Run state, Approvals, transitions

**Files:**
- Create: `plugins/ml-dev-kit/lib/mdk/run.py`
- Test: `plugins/ml-dev-kit/tests/test_run.py`

**Interfaces:**
- Consumes: `docs.*` from Task 2.
- Produces:
  - `class RunError(RuntimeError)`
  - `project_root(start: Path) -> Path`: uses `git rev-parse --show-toplevel` and raises `RunError` when the folder isn't in a git repo.
  - `@dataclass Run(root: Path, slug: str, state: dict)` with:
    - properties `dir`, `stage`, `awaiting`, `current`, `features`;
    - `feature(fid) -> dict`;
    - `spec_path(fid) -> Path`, which is `dir / f"{fid}-{feature-slug}.md"`.
  - `active_run(root: Path) -> Run | None`: the `docs/features/*/state.json` whose stage isn't `done`. Raises `RunError` if more than one.
  - `init_run(root: Path, slug: str, goal: str) -> Run`
  - `current_hash(run, kind: str, fid: str | None = None) -> str | None` and `is_approved(run, kind, fid=None) -> bool`, where kind is `standards`, `breakdown` or `spec`.
  - Transitions:
    - `request_approval(run, kind, fid=None) -> None`
    - `record_approval(run) -> dict | None`
    - `begin_build(run, fid) -> None`
    - `escalate(run, fid, reason) -> None`
    - `mark_done(run, fid) -> None`
    - `next_action(run) -> str`
  - State shape: `{"goal", "slug", "branch", "stage", "awaiting": None | {"kind", "feature"}, "current", "features": [{"id", "slug", "status", "base"}], "escalation"}`.
    - `stage` is one of `setup|breakdown|spec|build|escalated|done`.
    - Feature `status` is one of `pending|building|escalated|done`.
  - Records shape: `{"approvals": [{"kind", "feature", "sha256", "at"}], "done": [{"feature", "sha256", "at"}]}`, with `at` as UTC ISO time.

**Pinned transition rules:**
- `init_run`:
  - Rejects a bad slug, an active Run, a dirty tree (`git status --porcelain`), or an existing directory.
  - Runs `git switch -c mdk/<slug>`.
  - Sets stage to `setup` when `STANDARDS.md` is missing, otherwise `breakdown`.
- `request_approval`:
  - `standards`: needs stage `setup` and a `STANDARDS.md` that parses.
  - `breakdown`:
    - needs stage `setup` with standards approved, or stage `breakdown`;
    - `breakdown.md` must parse, and no feature may have left `pending`;
    - sets the features list and stage `breakdown`.
  - `spec`:
    - needs the breakdown approved, a feature with status `pending` or `escalated`, and no *other* feature `building`;
    - the spec file must exist with `spec_problems == []`; otherwise raise `RunError` listing the problems;
    - sets stage `spec` and `current`.
  - Every kind sets `awaiting`.
- `record_approval`:
  - Returns `None` if nothing is awaited.
  - Otherwise appends a record with `current_hash` and clears `awaiting`.
- `begin_build`:
  - Needs the spec approved and the spec file clean in git (`git status --porcelain -- <path>` is empty), meaning the Spec is committed.
  - Sets status `building`, `base` = HEAD sha (only if it's still `None`), stage `build`, and `escalation` `None`.
- `escalate`:
  - Needs status `building`.
  - Sets status `escalated`, stage `escalated`, and `escalation = {"feature", "reason", "at"}`.
- `mark_done`:
  - Needs stage `build` with `current == fid`.
  - Appends a done record and sets status `done`.
  - If a feature is still pending: `current` = that feature, stage `spec`. Otherwise: `current` = `None`, stage `done`.
- `next_action` returns one sentence per case:
  - It contains `approve` whenever `awaiting` is set.
  - It names the feature ID whenever one applies.
  - For escalated it includes the reason.
  - For `done` it says "Run complete."

- [ ] **Step 1: Write the failing tests.** They are listed below with their key assertions. Each test builds its repo with `make_repo` and the fixtures.
  - `test_init_creates_branch_and_state`: on a repo without `STANDARDS.md`:
    - stage is `setup`;
    - `git branch --show-current` is `mdk/accounts`;
    - `active_run(root).slug == "accounts"`.
  - `test_init_stage_breakdown_when_standards_exist`
  - `test_init_refuses_dirty_tree`, `test_init_refuses_second_run`, `test_init_rejects_bad_slug` (`"Bad Slug"`): each one does `assertRaises(RunError)`.
  - `test_project_root_requires_git`: a plain temporary folder raises `RunError`.
  - `test_await_breakdown_requires_standards_approval_in_setup`
  - `test_standards_approval_tracks_file_hash`:
    - after `request_approval(standards)` and then `record_approval`, the returned record's `sha256 == current_hash(run, "standards")` and `is_approved` is True;
    - after editing `STANDARDS.md`, `is_approved` is False.
  - `test_record_approval_without_awaiting_returns_none`
  - `test_await_spec_lists_spec_problems`: the `RunError` message contains `Out of scope` for a Spec missing that section.
  - `test_begin_requires_committed_spec`: an uncommitted Spec raises `RunError`.
  - `test_begin_records_base_and_stage_build`:
    - `feature("01")["base"]` equals HEAD;
    - stage is `build`.
  - `test_escalate_then_reapprove_keeps_base`: begin → escalate → edit the Spec body → await spec → record → commit → begin. The base is unchanged and the stage is `build`.
  - `test_mark_done_advances_to_next_feature`:
    - after 01, `current` is `02` and stage is `spec`;
    - after 02, stage is `done` and `active_run` is `None`.
  - `test_next_action_mentions_approve_when_awaiting`
- [ ] **Step 2:** Run the suite. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `run.py`.**
  - Write the state and records files as JSON with 2-space indentation and a trailing newline.
  - Write them atomically: write a temporary file in the same folder, then `os.replace`.
  - Run git through `subprocess.run([...], cwd=root, capture_output=True, text=True, check=False)`. A non-zero exit raises `RunError` with git's stderr.
- [ ] **Step 4:** Run the suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: track Run state and Approvals`

---

### Task 4: `check.py` — the mechanical Done check

**Files:**
- Create: `plugins/ml-dev-kit/lib/mdk/check.py`
- Modify: `plugins/ml-dev-kit/tests/helpers.py`. Add `build_ready_repo(tmp: Path, test_command: str) -> tuple[Path, Run]`. It runs a one-feature Run up to `begin_build("01")` and writes `STANDARDS.md` with the given command and ``Test files: `tests/**/*.py` ``.
- Test: `plugins/ml-dev-kit/tests/test_check.py`

**Interfaces:**
- Consumes: `run.Run`, `run.is_approved`, `docs.parse_standards`, `docs.behaviour_ids`, `docs.glob_to_regex`, `docs.mentions_id`.
- Produces:
  - `@dataclass CheckResult(passed: bool, problems: list[str], output_tail: str)`
  - `check_feature(run: Run, fid: str, timeout: int = 1800) -> CheckResult`

- [ ] **Step 1: Write the failing tests.**

```python
def test_passes_when_ids_covered_and_suite_green(self):
    root, run = build_ready_repo(self.tmp, "python3 -c \"print('ok')\"")
    write(root, "tests/test_x.py", "def test_01_B1(): pass\ndef test_01_B2(): pass\n")
    r = check_feature(run, "01"); self.assertTrue(r.passed, r.problems)
def test_fails_missing_behaviour_test(self):  # only 01_B1 present
    self.assertTrue(any("01-B2" in p for p in r.problems)); self.assertFalse(r.passed)
def test_fails_no_test_files(self): self.assertTrue(any("no test files" in p for p in r.problems))
def test_fails_red_suite(self):  # command prints 'boom' and exits 1
    self.assertFalse(r.passed); self.assertIn("boom", r.output_tail)
def test_fails_when_spec_changed_after_approval(self): self.assertTrue(any("Approval" in p for p in r.problems))
def test_timeout_reported(self):  # command sleeps 5, timeout=1
    self.assertTrue(any("timed out" in p for p in check_feature(run, "01", timeout=1).problems))
def test_missing_runner_reported(self):  # command 'definitely-not-a-command-xyz'
    self.assertFalse(check_feature(run, "01").passed)
```

- [ ] **Step 2:** Run the suite. Expected: FAIL.
- [ ] **Step 3: Implement `check_feature`.** It collects every problem rather than stopping at the first:
  1. The spec isn't approved for its current body. Problem text: `"Spec 01 has no current Approval"`.
  2. Find the test files: `git ls-files --cached --others --exclude-standard`, filtered by the globs. If there are none: `"no test files match <globs>"`.
  3. Each Behaviour ID must appear in at least one test file. Otherwise: `"no test names 01-B2"`.
  4. Run the test command with `subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)`:
     - non-zero exit: `"test command failed (exit N)"`;
     - `TimeoutExpired`: `"test command timed out after Ns"`.
  - `output_tail` is the last 40 lines of stdout and stderr combined.
  - `passed` is `not problems`.
- [ ] **Step 4:** Run the suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: mechanical Done check`

---

### Task 5: `hooks.py` — Edit gate and Approval capture

**Files:**
- Create: `plugins/ml-dev-kit/lib/mdk/hooks.py`
- Test: `plugins/ml-dev-kit/tests/test_hooks.py`

**Interfaces:**
- Consumes: `run.project_root`, `run.active_run`, `run.is_approved`, `run.record_approval`, `run.next_action`.
- Produces:
  - `APPROVE_RE = re.compile(r"^\s*approved?\s*[.!]?\s*$", re.IGNORECASE)`
  - `gate(event: dict) -> dict | None`: `None` means allow silently.
    - A deny is `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "ml-dev-kit: ..."}}`.
  - `on_prompt(event: dict) -> dict | None`
    - When it records an Approval, it returns `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "ml-dev-kit: recorded the human's Approval of <kind> <fid> (sha256 <first 12>)"}}`.
  - Each event carries `cwd`, `tool_name`, and `tool_input` (with `file_path`, `notebook_path` or `command`), or `prompt` for the prompt hook. The root comes from `project_root(Path(event["cwd"]))`. A `RunError` there means allow, or `None` for the prompt hook.

**Pinned gate rules.** The first match wins:

1. No git repo or no active Run → allow.
2. `Bash` whose command contains `state.json` or `records.json` → deny ("use mdk"). Any other Bash command → allow.
3. Edit, Write, MultiEdit or NotebookEdit: resolve the path against `cwd`.
   - A path outside the root → allow.
   - `docs/features/*/state.json` or `records.json` → deny.
   - `STANDARDS.md` → allow only in stage `setup`. Otherwise deny: "STANDARDS.md is human-owned".
   - `docs/**` or `CONTEXT.md` → allow.
   - Any other path → allow only when:
     - stage is `setup` and standards are approved; or
     - stage is `build` and the current spec is approved.
   - Otherwise deny, with `next_action(run)` in the reason.

- [ ] **Step 1: Write the failing tests.** Names and key assertions:
  - `test_gate_allows_outside_git`, `test_gate_allows_when_no_run`: `assertIsNone`.
  - `test_gate_denies_source_edit_before_spec_approval`: decision is `deny`, and the reason starts with `ml-dev-kit:`.
  - `test_gate_allows_docs_and_context_during_spec`
  - `test_gate_denies_state_and_records_edits` (in stage `build` too), `test_gate_denies_bash_mentioning_records`, `test_gate_allows_other_bash`
  - `test_gate_allows_source_edit_in_build`
  - `test_gate_denies_after_spec_body_changed`, `test_gate_allows_after_deviations_changed`
  - `test_gate_standards_only_in_setup`
  - `test_gate_setup_writes_need_standards_approval`
  - `test_gate_denies_in_escalated`
  - `test_gate_allows_paths_outside_repo` (path `/tmp/elsewhere.py`), `test_gate_resolves_relative_path_against_cwd` (`src/a.py` with `cwd` = root: denied before approval)
  - `test_prompt_records_approval_on_exact_token`:
    - `"approve"`, `"Approved!"` and `"  APPROVE.  "` each record;
    - the returned `additionalContext` contains `recorded`.
  - `test_prompt_ignores_other_text`:
    - `"don't approve yet"`, `"approve but change X"` and `"looks good"` return `None`;
    - `records.json` approvals are unchanged.
  - `test_prompt_ignores_when_nothing_awaiting`
- [ ] **Step 2:** Run the suite. Expected: FAIL.
- [ ] **Step 3:** Implement `gate` and `on_prompt` per the rules above.
- [ ] **Step 4:** Run the suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: Edit gate and Approval capture hooks`

---

### Task 6: `cli.py`, `bin/mdk`, `hooks/hooks.json`

**Files:**
- Create: `plugins/ml-dev-kit/lib/mdk/cli.py`, `plugins/ml-dev-kit/bin/mdk` (mode 755), `plugins/ml-dev-kit/hooks/hooks.json`
- Test: `plugins/ml-dev-kit/tests/test_cli.py`. It runs `[sys.executable, str(PLUGIN / "bin/mdk"), ...]` with `cwd` set to the repo.

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str]) -> int`.

| Command | Behaviour |
|---|---|
| `mdk init <slug> <goal...>` | `init_run` |
| `mdk status` | Prints JSON. With an active Run: `{"active": true, "slug", "goal", "branch", "stage", "awaiting", "current", "features", "escalation", "next"}`. Otherwise: `{"active": false}`. |
| `mdk await standards\|breakdown\|spec [NN]` | `request_approval`. Prints `next_action`. |
| `mdk begin NN` | `begin_build` |
| `mdk check NN [--timeout S]` | Prints PASS/FAIL, the problems and the output tail. Exit 0 on pass, 1 on fail. |
| `mdk done NN [--timeout S]` | `check_feature`, then `mark_done` on pass. Exit 1 on fail, leaving state unchanged. |
| `mdk escalate NN <reason...>` | `escalate` |
| `mdk hook gate\|prompt` | Reads the event JSON from stdin and prints the result JSON when there is one. |

**Errors and exit codes:**
- `RunError` and `DocError` print `mdk: <message>` to stderr and exit 2.
- `hook gate`: any exception → exit 2 with the message on stderr if `<cwd>/docs/features` exists, otherwise exit 0.
- `hook prompt`: any exception → warning on stderr, exit 0. It must never block the human's message.

**`bin/mdk`:** `#!/usr/bin/env python3`. It inserts `Path(__file__).resolve().parent.parent / "lib"` into `sys.path`, then runs `sys.exit(main(sys.argv[1:]))`.

**`hooks.json`:**
- `PreToolUse`: matcher `Edit|Write|MultiEdit|NotebookEdit|Bash`, command `python3 "${CLAUDE_PLUGIN_ROOT}/bin/mdk" hook gate`, timeout 10.
- `UserPromptSubmit`: command `python3 "${CLAUDE_PLUGIN_ROOT}/bin/mdk" hook prompt`, timeout 10.

- [ ] **Step 1: Write the failing tests.**
  - `test_status_no_run`: the output is `{"active": false}`.
  - `test_full_flow_through_cli`. With one feature in the breakdown:
    1. `init`, then write and commit `STANDARDS.md` (``Test command: `python3 -m unittest discover -s tests` ``).
    2. `await standards`, then `hook prompt` with stdin `{"prompt": "approve", "cwd": root}`.
    3. Write `breakdown.md`, `await breakdown`, approve.
    4. Write the Spec, `await spec 01`, approve, commit, `begin 01`.
    5. `check 01` → exit 1 (no tests yet).
    6. Write `tests/test_a.py` with passing tests named `test_01_B1` and `test_01_B2`.
    7. `check 01` → exit 0, then `done 01` → exit 0.
    8. `status` → `{"active": false}`.
  - `test_hook_gate_outputs_deny_json`: before approval, an Edit of `src/a.py` prints JSON with `permissionDecision` = `deny`.
  - `test_hook_gate_fails_closed_on_bad_state`: corrupt `state.json` → exit 2.
  - `test_hook_gate_fails_open_without_docs_features`: invalid stdin in a repo without `docs/features` → exit 0.
  - `test_errors_exit_2_with_message`: `begin 07` → exit 2, stderr starts with `mdk:`.
  - `test_bin_is_executable`
  - `test_hooks_json_wires_both_events`: it parses, has keys `PreToolUse` and `UserPromptSubmit`, and both commands contain `bin/mdk`.
- [ ] **Step 2:** Run the suite. Expected: FAIL.
- [ ] **Step 3:** Implement `cli.py`, `bin/mdk` (with `chmod +x`) and `hooks.json`.
- [ ] **Step 4:** Run the suite. Expected: PASS. Then run `claude plugin validate plugins/ml-dev-kit`. Expected: no errors.
- [ ] **Step 5:** Commit: `feat: mdk CLI and hook wiring`

---

### Task 7: Subagents — implementer, reviewer, spec-checker

**Files:**
- Create: `plugins/ml-dev-kit/agents/implementer.md`, `reviewer.md`, `spec-checker.md`
- Test: `plugins/ml-dev-kit/tests/test_plugin_files.py`. It needs a small `frontmatter(path) -> dict` helper that reads `key: value` lines between the first two `---` lines.

**Interfaces:**
- Produces three agent names: `implementer`, `reviewer` and `spec-checker`. Claude Code exposes them as `ml-dev-kit:<name>`. Each one's reply format, defined below, is what the orchestrator in Task 8 parses.

**Required content.** Each file stays under about 80 lines, uses `model: inherit`, and states why for each rule.

- **implementer**
  - Frontmatter: `disallowedTools: Agent`.
  - Inputs: the Spec path, `STANDARDS.md`, `CONTEXT.md`, the base commit and any review findings.
  - Rules:
    - Work test-first at the Spec's seams, one Behaviour at a time.
    - Name each test with its Behaviour ID (`test_01_B2_...`).
    - Capture each test's **failing output before** writing the code that makes it pass.
    - Reshape only the code the Feature touches, and follow `STANDARDS.md`.
    - Never edit the Spec, `STANDARDS.md`, `CONTEXT.md` or `docs/features/*/{state,records}.json`.
    - Use Context7 for library docs when it's available.
    - Don't commit.
  - Reply format:
    - `Status: DONE | DONE_WITH_CONCERNS | BLOCKED`
    - `Deviations:` a list of `what — why`
    - `Evidence:` for each Behaviour ID, the test name, its RED output excerpt and its GREEN result
    - `Noticed:` problems seen outside the Feature
- **reviewer**
  - Frontmatter: `tools: Read, Grep, Glob, Bash`. Bash is for `git diff <base>` and running tests only; it never changes files.
  - Inputs: the Spec, `STANDARDS.md`, the base commit, the implementer's report and the `mdk check` output.
  - It treats the implementer's report as unverified claims.
  - Reply format, two separate verdicts:
    - `## Spec and Deviations`:
      - every Deviation as `PASS` or `ESCALATE`, with one line tying it to the Intent or to scope;
      - behaviours that are missing, extra or wrong, each quoting the Spec line;
      - tests that pass without checking anything;
      - RED evidence that is missing or doesn't fit.
    - `## Standards`: findings against `STANDARDS.md` (architecture and docs), each marked `must-fix` or `note`.
    - Final line: `Verdict: CLEAN | FIX | ESCALATE`.
- **spec-checker**
  - Frontmatter: `tools: Read, Grep, Glob`.
  - It reads the draft Spec cold, as a builder who can't ask questions.
  - It replies with a ranked list of the places where a builder would have to guess and the guess would matter, or `nothing important left`.
  - It never comments on wording.

- [ ] **Step 1: Write the failing tests.**

```python
def test_agents_have_required_frontmatter(self):
    for name in ("implementer", "reviewer", "spec-checker"):
        fm = frontmatter(PLUGIN / f"agents/{name}.md"); self.assertEqual(fm["name"], name); self.assertTrue(fm["description"])
def test_implementer_cannot_spawn_agents(self): self.assertIn("Agent", frontmatter(PLUGIN / "agents/implementer.md")["disallowedTools"])
def test_read_only_agents_cannot_write(self):
    for name in ("reviewer", "spec-checker"):
        tools = frontmatter(PLUGIN / f"agents/{name}.md")["tools"]; self.assertNotIn("Write", tools); self.assertNotIn("Edit", tools)
def test_reviewer_reply_format(self):
    body = (PLUGIN / "agents/reviewer.md").read_text()
    for s in ("## Spec and Deviations", "## Standards", "Verdict:"): self.assertIn(s, body)
```

- [ ] **Step 2:** Run the suite. Expected: FAIL.
- [ ] **Step 3:** Write the three agent files with the required content.
- [ ] **Step 4:** Run the suite. Expected: PASS. Then run `claude plugin validate plugins/ml-dev-kit`.
- [ ] **Step 5:** Commit: `feat: implementer, reviewer and spec-checker agents`

---

### Task 8: Orchestrator skill, templates, README, NOTICE

**Files:**
- Create:
  - `plugins/ml-dev-kit/skills/feature/SKILL.md`
  - `references/{setup,spec,build}.md`
  - `templates/{spec,breakdown,standards}.md`
  - `NOTICE`
- Modify: `README.md`
- Test: add to `plugins/ml-dev-kit/tests/test_plugin_files.py`

**Interfaces:**
- Consumes:
  - the `mdk` commands from Task 6;
  - the agent names and reply formats from Task 7.
- The skill calls `mdk`, which is on PATH while the plugin is enabled. The fallback is `python3 "${CLAUDE_SKILL_DIR}/../../bin/mdk"`.

**Required content.** Keep it short. `SKILL.md` stays under about 80 lines, and each reference file under about 100.

**`SKILL.md`**
- Frontmatter:
  - `name: feature`
  - `description` (one sentence)
  - `disable-model-invocation: true`
  - `argument-hint: [goal]`
- Precedence: while a Run is active, this workflow governs. Don't hand off to other planning, brainstorming or execution skills, such as superpowers.
- Start:
  1. If the project isn't a git repo, offer `git init` plus an initial commit.
  2. Run `mdk status`.
  3. If a Run is active, resume at `next`. If a new Goal was given, say a Run is already active.
  4. If no Run is active and `$ARGUMENTS` is empty, ask for the Goal. Otherwise pick a slug and run `mdk init <slug> "<goal>"`.
- Route by stage:
  - `setup` → `references/setup.md`
  - `breakdown` and `spec` → `references/spec.md`
  - `build` and `escalated` → `references/build.md`
- Rules:
  - Only the human's own reply `approve` is an Approval. Ask for it in exactly those words. Never treat "looks good" as an Approval, and never record one yourself.
  - Questions to the human are decisions, one at a time, each with your recommended answer. Get facts from the code using Explore subagents.
  - Change Run state only through `mdk`.
  - Keep every doc short.

**`references/setup.md`**
1. Survey the project with Explore subagents: stack, test runner, layout, conventions.
2. Run the existing suite.
   - If tests fail: show the human, agree a Baseline, exclude those tests through the test command, and list them in the `## Baseline` section of `STANDARDS.md`.
   - If there's no test runner: propose one.
3. Draft `STANDARDS.md` from `templates/standards.md`, adjusting it with the human one question at a time.
4. Run `mdk await standards`, then ask for `approve`.
5. After the Approval: set up the runner if needed, commit, and continue in `references/spec.md`.

**`references/spec.md`**
- **Breakdown:**
  - Grill the human on the objective first; details come later.
  - Write `breakdown.md` from the template.
  - Run `mdk await breakdown`, ask for `approve`, then commit.
- **Each Feature:**
  1. Grill in the grill-with-docs style, updating `CONTEXT.md` inline and adding an ADR only when the decision is hard to reverse, surprising, and a real trade-off.
  2. Write `NN-<slug>.md` from the template. Its length should match the size of the Feature.
  3. Dispatch `ml-dev-kit:spec-checker` and bring the questions that matter to the human.
  4. Run `mdk await spec NN` and ask for `approve`.
  5. Commit the Spec, run `mdk begin NN`, and continue in `references/build.md`.

**`references/build.md`**
1. Dispatch `ml-dev-kit:implementer` with the packet.
   - If it reports `BLOCKED`, run `mdk escalate`.
2. Run `mdk check NN`.
3. Dispatch `ml-dev-kit:reviewer` with the packet, the base commit (from `mdk status`) and the check output.
4. Fix loop:
   - `FIX` → send the findings to the implementer, re-check and re-review. After **3** rounds, escalate.
   - `ESCALATE`, or a Deviation marked `ESCALATE` → run `mdk escalate NN "<reason>"` and put it to the human.
5. After a `CLEAN` verdict:
   - Append the passed Deviations to the Spec's `## Deviations` section. Touch no other part of the Spec.
   - Append the Noticed items to `noticed.md`.
   - Run `mdk done NN` (Bash timeout 600000).
   - Commit the code with the Spec.
   - Give the human a summary: what was built, the Deviations that passed, and what was noticed.
   - Go on to the next Feature.
- **Resolving an Escalation:**
  - The human decides; you amend the Spec body.
  - Run the spec-checker, `mdk await spec NN`, `approve`, commit, then `mdk begin NN`. The base commit is kept.
  - The fix-loop count resets.

**Templates**
- `templates/spec.md`:
  - the five section headings in the order of `SPEC_SECTIONS`;
  - one-line guidance under each;
  - a Behaviour line format `- **NN-B1** — <observable outcome>`;
  - `## Deviations` left empty, noted as "filled in by Build".
- `templates/breakdown.md`: a `# Breakdown: <goal>` header and the line format `NN. <feature-slug> — <one-line summary>`.
- `templates/standards.md`. The defaults:
  - **Architecture:** deep modules, small interfaces, one responsibility per file, and reshape only what the Feature touches.
  - **Documentation:** each module's doc says why; no comments that restate the code; short READMEs.
  - **Testing:** test through public interfaces at the agreed seams; test names carry Behaviour IDs; no tautological tests; mocks only at system boundaries.
  - The machine-read lines ``Test command: `<fill in>` `` and ``Test files: `<glob>` ``.
  - A `## Baseline` section.

**`README.md`** (at most about 60 lines)
- What it is, in 2 sentences.
- Install: `/plugin marketplace add cam-berger/ml-dev-kit`, then `/plugin install ml-dev-kit@ml-dev-kit`.
- Use: `/ml-dev-kit:feature <goal>`, and reply `approve` at each gate.
- What it writes into your project.
- Requirements: git and python3 ≥ 3.9.
- Develop: the test command and `claude plugin validate`.
- Links to the design and to `CONTEXT.md`.

**`NOTICE`**: the two MIT attributions from Global Constraints.

- [ ] **Step 1: Write the failing tests.**

```python
def test_feature_skill_is_user_only(self):
    fm = frontmatter(PLUGIN / "skills/feature/SKILL.md")
    self.assertEqual(fm["name"], "feature"); self.assertEqual(fm["disable-model-invocation"], "true"); self.assertIn("argument-hint", fm)
def test_skill_references_exist(self):
    for r in ("references/setup.md", "references/spec.md", "references/build.md"): self.assertTrue((PLUGIN / "skills/feature" / r).is_file())
def test_spec_template_sections_in_order(self):
    t = (PLUGIN / "skills/feature/templates/spec.md").read_text()
    idx = [t.index(f"## {s}") for s in SPEC_SECTIONS]; self.assertEqual(idx, sorted(idx))
def test_standards_template_parses(self):
    parse_standards((PLUGIN / "skills/feature/templates/standards.md").read_text())
def test_build_reference_caps_fix_loop_at_3(self): self.assertIn("3", (PLUGIN / "skills/feature/references/build.md").read_text())
def test_notice_attributes_sources(self):
    n = (REPO / "NOTICE").read_text(); self.assertIn("Matt Pocock", n); self.assertIn("Jesse Vincent", n)
```

- [ ] **Step 2:** Run the suite. Expected: FAIL.
- [ ] **Step 3:** Write the skill, references, templates, README and NOTICE with the required content.
- [ ] **Step 4:** Run the suite. Expected: PASS. Then run `claude plugin validate .` and `claude plugin validate plugins/ml-dev-kit`. Expected: no errors.
- [ ] **Step 5:** Commit: `feat: feature orchestrator skill, templates and docs`

---

## Acceptance (with the human, after all tasks)

Dogfood one small Run on a throwaway Python project, with the plugin loaded through `claude --plugin-dir plugins/ml-dev-kit`. Check that:

- the source edit is denied until `approve`;
- `approve` is recorded;
- the Done check blocks a missing Behaviour test;
- the Run ends with commits on `mdk/<slug>`.

This needs the human, because only a typed `approve` can unlock the gates.
