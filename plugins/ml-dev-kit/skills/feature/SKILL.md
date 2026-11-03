---
name: feature
description: Runs one Goal through a Breakdown and Specs the human approves, then builds, reviews and tests each Feature against its Spec.
disable-model-invocation: true
argument-hint: "[goal]"
---

# Feature workflow

A Run carries one Goal. The human co-writes and approves the Breakdown (the Features, in build order) and each Feature's Spec. After a Spec's Approval, subagents build and review that Feature without the human, and `mdk` records it as Done only when its check passes. The Run's files live in `docs/features/<run-slug>/` and its work on the branch `mdk/<run-slug>`.

Goal given with the command (may be empty): $ARGUMENTS

`mdk` is on PATH while this plugin is enabled. If the shell cannot find it, use `python3 "${CLAUDE_SKILL_DIR}/../../bin/mdk"` in its place for the rest of the Run.

## Start

1. Run `git rev-parse --show-toplevel`. If it fails, the project is not a git repo, and a Run needs one for its branch and commits. Offer to run `git init`, then `git add -A && git commit --allow-empty -m "Initial commit"`. Stop if the human declines.
2. Run `mdk status`. It prints JSON with `active`, `stage`, `awaiting`, `current`, `features`, `escalation` and `next`, the step to take now.
3. If `active` is true, resume: tell the human in a line where the Run stands, then route by stage below. If a Goal was also given, say that Run `<slug>` is still active and must finish first.
4. If no Run is active and no Goal was given, ask for the Goal. Otherwise pick a short slug for it (lowercase words joined by hyphens, such as `user-accounts`) and run `mdk init <slug> "<goal>"`, then `mdk status` again. `init` needs a clean working tree. If it refuses, show the human why and offer the fix.

## Route by stage

Open the reference for the `stage` that `mdk status` shows, and pick up at the step that `next` describes:

- `setup` → [references/setup.md](references/setup.md)
- `breakdown` or `spec` → [references/spec.md](references/spec.md)
- `build` or `escalated` → [references/build.md](references/build.md)

## Rules

These hold in every stage.

- While a Run is active, this workflow governs. Don't hand off to other planning, brainstorming or execution skills, such as superpowers. Their steps and gates are not the ones `mdk` checks.
- Only the human's own reply `approve` is an Approval. After each `mdk await`, give the document's path and a short summary, then ask in exactly these words: "Reply `approve` to approve <the document>, or tell me what to change." Never take "looks good" or "yes" as an Approval, and never record one yourself. A hook records the reply and adds a note saying so.
- When the human replies `approve`, run `mdk status` and check that `awaiting` is null before you go on. Never assume the hook recorded it. If it is not null, say the Approval was not recorded, do what the hook's note says, and ask again.
- If the human asks for changes instead, make them, run the same `mdk await` again so `mdk` re-checks the document, and ask again. An Approval covers the document exactly as `mdk await` checked it; after any later edit the hook refuses to record it.
- Never edit an approved document: `STANDARDS.md`, the Breakdown, or a Spec above its `## Deviations` heading. The Approval covers that text. If one has to change, tell the human why, change it, run its `mdk await` again and ask for a new Approval. During Build that goes through an Escalation. After setup only the human edits `STANDARDS.md`; if a rule in it gets in the way, tell them.
- Questions to the human are decisions. Ask one at a time, each with your recommended answer. Get facts from the code with Explore subagents: asking the human what the code can answer wastes the attention their decisions need.
- Read and change Run state only through `mdk`. A hook blocks `state.json` and `records.json`. When an `mdk` command fails it prints `mdk: <reason>`, and when the hook denies a tool call its reason starts `ml-dev-kit:`. Do what the reason says, or tell the human. Never make the change another way, such as Bash, `sed` or `cat`: the gates are how the human keeps control of the Run.
- Commit with `git add -A && git commit -m "<short message>"`. The tree was clean when the Run began, so every change belongs to the Run. Never push.
- Keep every doc short, and say why rather than what. Long docs go unread, and the why is what the code cannot show.
