# Codex host adapter

Read this before Start when the Feature workflow runs in Codex. Use the shared setup, Spec and Build references; this file only translates host-specific mechanics.

## Prerequisites and commands

- Use an installed local plugin in a Codex runtime with lifecycle hooks. The human must enable hooks and review and trust this plugin's hook definitions before the Run: `/hooks` in the CLI, or Settings > Hooks in the desktop app. If hooks are unavailable, disabled or untrusted, stop and point to the README's Codex setup; installing a standalone skill does not install the gates. Never invoke `mdk hook` yourself to simulate trust or an Approval.
- Invoke the skill explicitly, such as `$ml-dev-kit:feature add user accounts`, or select the plugin's Feature skill in the app. Read the Goal from the human's message; `$ARGUMENTS` and `${CLAUDE_SKILL_DIR}` are Claude substitutions, not Codex variables.
- Find `bin/mdk` from the absolute installed skill path: `skills/feature/../../bin/mdk`. Use that absolute path with `python3` throughout this Run, including in subagent packets. `${PLUGIN_ROOT}` exists in hook commands; do not assume it exists in the agent's shell.
- Codex sends shell hooks as `Bash` and patch hooks as `apply_patch`, with the patch in `tool_input.command`. The shared gate checks every add, update, delete and move path. Other edit tools and arbitrary shell writes are not completely covered: never route a denial through another tool.

## Dispatching roles

Claude's `ml-dev-kit:implementer`, `ml-dev-kit:spec-checker` and `ml-dev-kit:reviewer` names identify the Markdown role files in `../../../agents/` relative to this reference. Codex does not register these as named agent types.

1. Use the available subagent tool (for example `spawn_agent`) to start a fresh child. Use a clean context when supported (`fork_turns: "none"`); supply all inputs explicitly. Do not assume a particular model name or agent type exists.
2. Read the corresponding role file and put its full instructions in the child's prompt, followed by the packet the stage reference requests, the project root and the absolute `mdk` command. Claude frontmatter does not configure Codex permissions: explicitly tell spec-checkers and reviewers to remain read-only, and tell implementers not to spawn agents or commit.
3. Explore subagents are ordinary fresh children given a read-only code survey. For the three shipped roles, preserve their reply formats and keep implementation and review in separate children.
4. Continue an implementer for fix rounds using the available resume or follow-up tool (for example `followup_task`), including findings and check output. If it cannot be continued, dispatch a fresh child with its last cumulative report as the Build reference says. `SendMessage` is a Claude-specific example, not a required tool name.
5. Wait for each child's actual result before routing on its status or verdict. Send a short progress update while waiting. If subagent tools are unavailable, stop and explain that this workflow requires them; enable Codex multi-agent support and resume. Do not replace the separate Reviewer with self-review.

## Long checks

The Build reference's Bash timeout is a host detail. Use `mdk check NN --timeout 540` and `mdk done NN --timeout 540` unchanged. In Codex, launch with `exec_command`; if it yields a session ID, poll that session with `write_stdin` until its exit code and full result arrive. A yielded command has not passed. Leave enough total time for the 540-second suite cap and send progress while waiting; a short yield interval must not become the suite's timeout.

Approvals still come only from the human's own `approve` reply through `UserPromptSubmit`. After every such reply, run `mdk status` and require `awaiting` to be null before continuing, exactly as the shared skill requires.
