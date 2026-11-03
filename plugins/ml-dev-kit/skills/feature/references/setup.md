# Setup

Stage `setup` runs once per project, on its first Run. It ends with an approved `STANDARDS.md` at the project root: the rules Build follows and the Reviewer enforces, and the test command the Done check runs. If `next` says `STANDARDS.md` is approved, go straight to step 5.

1. Survey the project with Explore subagents: the stack, the test runner and how the suite is run, the layout, and the conventions in use. Ask them where the code falls short of [../templates/standards.md](../templates/standards.md). A new, empty project has nothing to survey; its stack is then the first decision to put to the human.
2. Run the existing test suite.
   - If tests fail, show the human which ones. Agree a Baseline with them: the failures that already existed. Exclude those tests through the test command (for example pytest's `--deselect`), and list them under `## Baseline` in `STANDARDS.md`. The Done check sees only the command's exit code, so a failure left in would block every Feature.
   - If there is no test runner, propose one that fits the stack.
3. Draft `STANDARDS.md` from the template. Go through it with the human: keep each default, change it, or drop it, and show where the survey found the code falls short. Fill in the two lines `mdk` reads:
   - ``Test command: `...` `` runs the whole suite, excluding the Baseline, and exits 0 when it passes.
   - ``Test files: `...` `` lists globs for the test files, comma-separated. The Done check looks in these files for a test named after each Behaviour ID.
4. Run `mdk await standards`, then ask for `approve`.
5. After the Approval, source edits are allowed. Set up the test runner if one was agreed, and run the test command once (in a project with no tests yet, a "no tests ran" result is fine). Commit, then write the Breakdown with [spec.md](spec.md).
