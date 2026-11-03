# Codex support implementation plan

**Goal:** Make the existing Feature workflow installable and usable in Codex, with its Approval and Done checks, while retaining Claude Code support.

**Architecture:** Both hosts load the same Python CLI, hooks, skill, templates and role instructions. A Codex marketplace and manifest add discovery; a patch-path reader sends every Codex edit through the existing gate. Codex dispatch instructions map the shipped roles onto its available subagent tools.

**Tech stack:** Python 3.9 or later, standard library only, git, Claude Code and a Codex runtime supporting trusted lifecycle hooks and subagents.

**Spec:** The user's request to add Codex functionality to the existing plugin, preserving the workflow described in `docs/specs/2026-11-03-feature-workflow-plugin-design.md`.

## Constraints

- Edit this checkout, never the installed Claude marketplace copy.
- Preserve Run files, approval hashes, exact approval tokens, stages and Done checks.
- Keep one shared skill and role set; do not introduce a second state format or a self-approval command.
- Codex hooks must be enabled and trusted by the human. Hook installation is not hook trust.
- Hook coverage is a workflow guardrail; shell edits and specialized tools are not a security boundary.

## Review focus

- A patch can mix allowed docs with unapproved source edits; one denied path denies the whole call.
- A move affects its original path and destination, including protected records and Standards.
- Paths resolve against the event cwd, including relative paths, symlinks and case variants.
- Malformed patches in an active Run deny; hooks outside a Run stay inert.
- Native plugin discovery must load the same resources, and Claude plugin validation must still pass.

## Steps

- [x] Add failing integration tests for patch edits, CLI Approval flow and Codex packaging in `tests/test_codex.py`.
- [x] Add `mdk.patch.patch_paths(command)` and reuse the existing file policy from `mdk.hooks.gate` for each patch path.
- [x] Add `.agents/plugins/marketplace.json` and `.codex-plugin/plugin.json`, referencing shared skills and hooks; bump manifests together to 0.2.0.
- [x] Adapt the skill entry point and add a Codex reference for command resolution, trusted hooks, role dispatch and long-running checks.
- [x] Run the Python suite, both Claude validators, Codex marketplace discovery, and an independent review before committing and pushing.

## Evidence

- Baseline: all 223 tests passed.
- Before implementation: 13 Codex integration tests produced 25 failing subcases and two missing-manifest errors; unchecked patches were the observed failure.
- Final Python suites: 241 tests passed on Python 3.14.7 and on the supported floor, Python 3.9.6.
- Claude marketplace and plugin manifests both passed `claude plugin validate`; `git diff --check` passed.
- Native Codex 0.166.0-alpha.5.1 discovered version 0.2.0, loaded `ml-dev-kit:feature`, and reported both shared hook events from the plugin. Validation used temporary process configuration and read-only resource loading, without installing or trusting hooks.
- Independent review reproduced three patch issues against the actual Codex executable: indented directives, leading filename spaces, and removing symlink entries. Each gained a failing regression before its fix. The gate now refuses ambiguous indentation, preserves filename spaces, and checks both directory entries and content targets.
- Shared Claude frontmatter remains for compatibility; the native Codex skill loader accepts it. Codex's invocation policy lives in `agents/openai.yaml`.
