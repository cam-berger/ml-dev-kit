# ml-dev-kit

A plugin for Claude Code and Codex that takes one Goal at a time through Specs you approve, then builds and tests each Feature against its Spec. You decide what gets built, and the agent follows your written Standards for how.

## Install in Claude Code

```
/plugin marketplace add cam-berger/ml-dev-kit
/plugin install ml-dev-kit@ml-dev-kit
```

Start a Run with `/ml-dev-kit:feature add user accounts`, or resume with `/ml-dev-kit:feature`.

## Install in Codex

Use the OpenAI Codex CLI with plugin support:

```
codex plugin marketplace add cam-berger/ml-dev-kit
codex plugin add ml-dev-kit@ml-dev-kit
```

You can also add this checkout with `codex plugin marketplace add /path/to/ml-dev-kit` and install ML Dev Kit from that marketplace in the desktop Plugins Directory. The CLI commands and desktop availability depend on your Codex version.

Enable lifecycle hooks and multi-agent support in Codex, then review and trust the plugin's hooks with `/hooks` in the CLI or Settings > Hooks in the desktop app. Restart or open a new chat after installation. Installing the skill alone does not install the approval gates. Hooks run locally; this package is for manual installation, not the public plugin directory. See [Codex hooks](https://learn.chatgpt.com/docs/hooks) and [plugin setup](https://developers.openai.com/plugins/build/plugins).

Select the plugin's Feature skill, or type `$ml-dev-kit:feature add user accounts`. Use `$ml-dev-kit:feature` with no Goal to resume. Codex uses the same stages, Run records, approval hashes and test checks as Claude Code. Its subagents follow the shipped implementer, spec-checker and reviewer instructions; see the [Codex adapter](plugins/ml-dev-kit/skills/feature/references/codex.md).

## Use

The plugin asks one decision at a time, each with its recommended answer, and looks facts up in the code. At each gate (Standards, the Breakdown, each Spec), reply `approve`. After a Spec's Approval it builds, tests and reviews that Feature without you, returning only if something needs your decision. Start in the project root so hooks find the Run.

A prompt hook records your Approval. The edit hook checks Claude file edits and every path in a Codex patch, including both sides of a move, and blocks source edits until the current Spec is approved. A Feature is Done only when every Behaviour has a named test, the suite's output shows it ran, and the suite passes. Hooks are workflow guardrails: arbitrary shell writes and specialized edit tools are not completely covered, and the agent must never work around a denial.

Once installed and trusted, the hooks run in every Claude Code session or Codex session using the enabled plugin, and do nothing without an active Run. The Done check stops the test suite after 540 seconds; keep the test command under about 8 minutes.

To abandon a Run, switch back to your own branch, delete `docs/features/<goal-slug>/` if still present, and delete the Run branch: `git branch -D mdk/<goal-slug>`.

## What it writes into your project

- `STANDARDS.md`: your architecture, docs and testing rules, and a test command that prints each test's name. Written with you on the first Run; after that, only you change it.
- `CONTEXT.md`: the project's domain language, updated as terms settle.
- `docs/adr/`: decision records for decisions that are hard to reverse.
- `docs/features/<goal-slug>/`: `breakdown.md`, one Spec per Feature (`NN-<feature-slug>.md`), `noticed.md` (problems seen outside a Feature), and `state.json` and `records.json`, which only the plugin writes.

Each Run works on branch `mdk/<goal-slug>` and commits locally. Nothing is pushed by the workflow.

## Requirements

git and python3 3.9 or later (standard library only). Codex also needs a runtime with trusted lifecycle hooks and subagent tools.

## Develop and update

```
python3 -m unittest discover -s plugins/ml-dev-kit/tests -v
claude plugin validate .
claude plugin validate plugins/ml-dev-kit
codex plugin list --marketplace ml-dev-kit --available --json
```

For local Claude testing, start in a project with `claude --plugin-dir <repo>/plugins/ml-dev-kit`. For Codex discovery, run the list command from this repository after adding it as a local marketplace.

Make changes in your development checkout, commit and push, then refresh the installed marketplace: `claude plugin marketplace update ml-dev-kit` for Claude Code, or `codex plugin marketplace upgrade ml-dev-kit` for Codex. Reinstall or refresh the installed plugin if your client requires it, and review updated hooks when prompted. Never edit either client's installed cache.

## Read more

- [Design](docs/specs/2026-11-03-feature-workflow-plugin-design.md): why the workflow works this way.
- [CONTEXT.md](CONTEXT.md): the domain language (Run, Goal, Feature, Spec, Approval and the rest).
- [NOTICE](NOTICE): the MIT-licensed projects it adapts.
