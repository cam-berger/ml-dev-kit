# Feature Workflow Plugin — Design

Date: 2026-11-03 · Status: approved 2026-11-03 · Domain language: [CONTEXT.md](../../CONTEXT.md)

## 1. Intent

AI-built features tend to fall apart once they are tested and built on. Usually the agent guessed at things nobody specified, wrote tests that check nothing, or bolted code on with no structure. This plugin exists so the codebases it produces are **explainable** (you can read them and their docs and understand why they are the way they are) and **easy to build on**. It gets there by putting the human in charge of *what* gets built and holding the agent to written standards for *how*.

Success looks like this: a human can come back to a project months later, read its Specs, CONTEXT.md and docs, and extend it without archaeology. A new Feature doesn't break an old one.

## 2. Goals

- One command starts a **Run** for one **Goal**. The human co-writes the **Breakdown** and each **Spec**, and approves each.
- After a Spec's **Approval**, Build and Test run without the human. A **Reviewer** agent judges every **Deviation**: it passes ones that trace to the **Intent** without changing scope and **Escalates** the rest.
- A Feature is **Done** only when every Spec behaviour has a test written before its code *and* the full test suite passes.
- Each project has one **Standards** file covering architecture, docs and testing. The human sets it on the first Run from shipped defaults. Build follows it and the Reviewer enforces it.
- Works on new and existing projects.

## 3. Non-goals (v1)

- Opening PRs, pushing, issue trackers, CI integration.
- Building several Features in parallel.
- Repo-wide refactoring or cleanup. That is its own Goal, asked for explicitly.
- Frontend visual design. Impeccable already covers that, and the plugin can point to it.

## 4. Anti-goals (failure even if it "works")

- **Specs longer than the change.** Spec length scales with the Feature. A small Feature gets a short Spec.
- **Silent Spec drift.** Code does something the Spec doesn't say, and nobody recorded it.
- **Asking the human what the codebase can answer.** Questions are for decisions, never for facts.
- **The plugin becoming slop itself:** many commands, many files per Feature, long prompts nobody reads.
- **Prose-only gates.** Research consistently shows agents skip instructions. Any rule that must always hold is enforced mechanically.

## 5. Decisions made with the human

These were settled in the grilling session; terms are defined in CONTEXT.md.

1. A Run carries one Goal. A Goal splits into one or more Features, and each passes Spec → Build → Test before the next starts.
2. The human is in the loop while the Breakdown and every Spec are written. Approval of a Spec is the last human gate before Build.
3. The Reviewer passes a Deviation only if it traces to the Intent and does not materially change scope. Otherwise it becomes an Escalation that pauses the Feature for the human.
4. Done = every Spec behaviour has a test written before its code, plus a passing full suite.
5. One Standards file per project, written with the human from shipped defaults. Only the human changes it.
6. One command, given the Goal, starts the Run.
7. New and existing projects. Build only reshapes code the Feature touches; problems elsewhere are reported, not fixed.
8. **Failing or missing tests.**
   - At Setup, test failures that already exist are recorded as a baseline and shown to the human. Done then means: every test for this Feature passes, and the suite has no failures beyond that baseline.
   - If there's no test runner, setting one up is part of Setup, with the human's approval.
9. **Git is required.**
   - Setup offers `git init` when a project has none.
   - Each Run works on its own branch.
   - The plugin commits locally: the Spec when it's approved, the code when a Feature is Done. It never pushes.
10. **Test-first evidence.** For each Behaviour, the implementer must capture its test failing before writing the code. The Reviewer checks that evidence. Commit-level proof of the order is out of scope for v1.

## 6. How it works

### 6.1 Shape

A self-contained plugin with:

- **One user-invoked skill** (the orchestrator) with `disable-model-invocation: true`, taking the Goal as its argument. It runs in the **main conversation** because subagents cannot ask the user questions, and Spec and Approval need the human.
- **Three subagents** in `agents/`:
  - **implementer**: writes tests and code for one Feature.
  - **reviewer**: judges Deviations, Standards and test quality.
  - **spec-checker**: reads a draft Spec cold and lists the ambiguities a builder would have to guess at. This runs before the human is asked to approve, because reviewing a spec for ambiguity is a different job from reviewing a diff.
- **One plugin-level hook:** the Build gate (6.6).
- **Read-only Explore subagents** (built in) to answer factual questions about the codebase during Spec, so the human is only asked to decide.

**Not used:** the built-in Workflow tool. It cannot take mid-run input and is opt-in per plan, while this design needs human turns between stages.

### 6.2 Stage 0 — Setup (first Run in a project only)

If no Standards file exists:

1. On an existing project, survey the code with Explore subagents (structure, test runner, conventions) and show where it falls short of the defaults.
2. Grill the human briefly to adjust the defaults, then write the **Standards** file.

The Standards file must record the project's **test command**, because Done depends on running it.

### 6.3 Stage 1 — Spec (human in the loop)

1. **Breakdown.** Grill the human on the Goal and objective first, details later. Propose how the Goal splits into Features and in what order. The human edits and approves. A Goal that is one Feature has a one-line Breakdown.
2. **Per Feature, before Build:**
   - Grill on that Feature in the grill-with-docs style: one decision at a time, each with a recommended answer. Update CONTEXT.md and ADRs inline.
   - Draft the Spec, run the spec-checker, and bring its questions to the human.
   - Ask for Approval.
3. **What every Spec contains:**
   - **Intent**: the why, in a few sentences.
   - **Behaviours**: each with a stable ID (e.g. `B1`), written as observable outcomes.
   - **Interface and seams**: the public interface, plus where tests attach, agreed with the human.
   - **Out of scope.**
   - **Deviations**: empty at Approval; filled in during Build.

### 6.4 Stage 2 — Build (no human)

1. The implementer subagent gets the Spec, the Standards and CONTEXT.md.
2. It works test-first at the agreed seams: write a failing test for a Behaviour, then make it pass, Behaviour by Behaviour. Each test names its Behaviour ID.
3. It may reshape only existing code the Feature touches. It may use Context7 for library docs when that is available.
4. It reports back:
   - a status: done, done-with-concerns, or blocked;
   - every Deviation it made, with the reason;
   - its test evidence.

### 6.5 Stage 3 — Test and Review (no human unless Escalated)

1. The orchestrator runs the **full test suite** itself, using the command from the Standards file. It does not trust the implementer's claim.
2. **Mechanical Done check.** It fails if any of these hold:
   - a Spec Behaviour ID has no test naming it;
   - zero tests ran;
   - the suite does not pass.
3. The **reviewer** subagent gets the Spec, Standards, diff and implementer report, and treats the report as unverified claims. It produces two separate verdicts:
   - **Spec and Deviations:** for each Deviation, *pass* (traces to the Intent, no scope change) or *escalate*. It also flags behaviours that are missing, extra or wrong, and tests that pass without checking anything.
   - **Standards:** architecture and docs against the Standards file.
4. **Fix loop.** Findings go back to the implementer. After **3 rounds** without a clean result, the remaining issues become an Escalation.
5. **Recording.** Passed Deviations are written into the Spec's Deviations section. Problems seen outside the Feature are added to a "noticed, not fixed" list for the human.
6. **Feature Done.** The orchestrator gives the human a short summary: what was built, the Deviations that passed, and what it noticed. Then it moves on to the next Feature's Spec.

### 6.6 Enforcement

Approval and Done must be impossible for the agent to fake, so neither is a flag the model writes itself:

- **Approval** is recorded by a hook from the human's own answer, not by the orchestrator writing `state.json`.
- **Done** is recorded only by the check script, and only when it has just passed.
- **Edit gate.** A PreToolUse hook on `Edit|Write` blocks changes to project files outside the plugin's own folder unless the current Feature's Spec has a recorded Approval. It also blocks the agent from writing the approval and done records directly. It does nothing when no Run is active.

The Edit gate guards against accidents; it is not a security boundary, since Bash can still write files.

### 6.6a Resolving an Escalation

1. The human amends the Spec.
2. The amended Spec goes back through the spec-checker and needs a new Approval.
3. Build keeps the code already written and continues against the amended Spec. The Reviewer re-checks the whole Feature diff against it.
4. The fix-loop count resets.

### 6.7 Files in the user's project

```
STANDARDS.md                      # per-project Standards (human-owned)
CONTEXT.md                        # domain language (grill-with-docs format)
docs/adr/                         # only when an ADR is warranted
docs/features/<goal-slug>/
  breakdown.md                    # approved Breakdown
  NN-<feature-slug>.md            # one Spec per Feature
  state.json                      # where the Run is; read on resume
```

Specs and the Breakdown are committed. They are part of the project's documentation.

### 6.8 Resume

Running the command again with no Goal resumes the active Run from `state.json`, at whatever is waiting: an Approval, an Escalation, or the next Feature. It never relies on chat memory.

## 7. Choices I made (the human hasn't ruled on these)

- **Self-contained, no plugin dependencies.** The grilling, TDD and review prompts are adapted from mattpocock/skills (MIT) and superpowers (subagent-driven-development, task reviewer), with attribution. Two reasons:
  - The mattpocock `grill-with-docs` and `implement` skills are user-only and can't be called.
  - Depending on superpowers would bring its SessionStart hook, which pushes its own brainstorming and planning flow and its "never pause, make rulings" execution style. That conflicts with this design.
- **One TDD style:** Matt Pocock's. Seams are agreed in the Spec, it goes one test then one implementation, and refactoring happens at review.
- **CONTEXT.md** for domain language, matching the grill-with-docs you have installed. Not GLOSSARY.md.
- **Fix loop cap of 3** before an Escalation.
- **Context7 and Impeccable are optional.** They are used if present and never required.
- **Doc concision** is checked by the reviewer against the Standards file. There is no separate prose pass.
- **Approval and Done can't be faked** (6.6). This takes a few small hooks rather than one, a cost accepted to keep gates mechanical.
- **Escalation handling** (6.6a): keep the code, re-check the amended Spec, reset the fix count.

## 8. Left to the builder

- Exact prompt wording, file names inside the plugin, and the `state.json` schema.
- How Behaviour IDs are matched to tests, provided it is mechanical.
- The default Standards content, within the principles above: deep modules, small interfaces, concise docs that explain *why*, test-first.
- Choice of models per subagent.
- How the plugin itself is tested: at minimum `claude plugin validate`, plus one dogfood Run on a small sample project.

## 9. Open questions for the human

None. The builder check's three open questions were answered as decisions 8–10.
