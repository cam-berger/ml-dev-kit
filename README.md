# ml-dev-kit

A Claude Code plugin that takes one Goal at a time through Specs you approve, then builds and tests each Feature against its Spec. The aim is a codebase you can read and extend months later: you decide what gets built, and the agent is held to your written Standards for how.

## Install

```
/plugin marketplace add cam-berger/ml-dev-kit
/plugin install ml-dev-kit@ml-dev-kit
```

On Claude Code 2.1.275 or later this also works in one step:

```
/plugin install ml-dev-kit --marketplace cam-berger/ml-dev-kit
```

## Use

```
/ml-dev-kit:feature add user accounts
```

The plugin asks you one decision at a time, each with its recommended answer. It looks facts up in the code itself. At each gate (your Standards, the Breakdown, each Spec) reply `approve`; that exact word is the only thing it accepts as an Approval. After a Spec's Approval it builds, tests and reviews the Feature without you, and comes back only if something needs your decision. Run `/ml-dev-kit:feature` with no Goal to resume a paused Run. Start Claude Code in the project root: the hooks find the Run from the folder Claude Code runs in.

The gates are mechanical. A hook records your `approve`, source edits are blocked until the current Spec is approved, and a Feature is Done only when every Behaviour has a test named after it, the suite's output shows that test ran, and the suite passes. Once installed, the plugin's hooks run in every Claude Code session, and do nothing in a project with no active Run. The Done check stops the test suite after 540 seconds, so keep the test command under about 8 minutes.

To abandon a Run, switch back to your own branch, delete `docs/features/<goal-slug>/` if it is still there, and delete the Run's branch: `git branch -D mdk/<goal-slug>`.

## What it writes into your project

- `STANDARDS.md`: your rules for architecture, docs and testing, and a test command that prints each test's name. Written with you on the first Run; after that, only you change it.
- `CONTEXT.md`: the project's domain language, updated as terms are settled.
- `docs/adr/`: decision records, only for decisions that are hard to reverse.
- `docs/features/<goal-slug>/`: `breakdown.md`, one Spec per Feature (`NN-<feature-slug>.md`), `noticed.md` (problems seen outside a Feature and not fixed), and `state.json` and `records.json`, which only the plugin writes.

Each Run works on its own branch, `mdk/<goal-slug>`, and commits locally. Nothing is pushed.

## Requirements

git, and python3 3.9 or later (standard library only).

## Develop

```
python3 -m unittest discover -s plugins/ml-dev-kit/tests -v
claude plugin validate .
claude plugin validate plugins/ml-dev-kit
```

To try a local copy in a project, start Claude Code there with `claude --plugin-dir <path to this repo>/plugins/ml-dev-kit`.

## Read more

- [Design](docs/specs/2026-11-03-feature-workflow-plugin-design.md): why the plugin works this way.
- [CONTEXT.md](CONTEXT.md): the plugin's domain language (Run, Goal, Feature, Spec, Approval and the rest).
- [NOTICE](NOTICE): the MIT-licensed projects it adapts.
