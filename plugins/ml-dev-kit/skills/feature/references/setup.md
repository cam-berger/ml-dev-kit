# Setup

Stage `setup` runs once per project, on its first Run. It ends with an approved `STANDARDS.md` at the project root: the rules Build follows and the Reviewer enforces, and the test command the Done check runs. If `next` says `STANDARDS.md` is approved, go straight to step 6.

1. Survey the project with Explore subagents: the stack, the test runner and how the suite is run, the layout, and the conventions in use. Ask them where the code falls short of [../templates/standards.md](../templates/standards.md). A new, empty project has nothing to survey; its stack is then the first decision to put to the human.
2. Run the existing test suite.
   - If tests fail, show the human which ones. Agree a Baseline with them: the failures that already existed. Exclude those tests through the test command (for example pytest's `--deselect`), and list them under `## Baseline` in `STANDARDS.md`. The Done check sees only the command's exit code, so a failure left in would block every Feature.
   - If there is no test runner, propose one that fits the stack.
3. Draft `STANDARDS.md` from the template. Go through it with the human: keep each default, change it, or drop it, and show where the survey found the code falls short. Fill in the two lines `mdk` reads:
   - ``Test command: `...` `` runs the whole suite, excluding the Baseline, and exits 0 when it passes.
   - ``Test files: `...` `` lists globs for the test files, each in its own backticks, comma-separated. The Done check looks in these files for a test named after each Behaviour ID.
4. Check both lines before they lock. After setup only the human can change them, so a broken line would fail every Done check in Build, where the human is out of the loop and the implementer cannot fix it.
   - Run the drafted test command and time it (Bash timeout 600000). It must exit 0. If it fails, fix the command, or agree the Baseline again with the human. If it takes more than about 8 minutes, agree a faster command with the human: the Done check stops the suite at 540 seconds.
   - For each glob, run `git ls-files -co --exclude-standard ':(glob)<glob>'`. This lists the files the Done check will search. If a glob lists none of the project's test files, fix it.
   - In a new project with no runner or tests yet, check that the globs cover where the test command looks for tests, and run the command in step 6 instead.
5. Run `mdk await standards`, then ask for `approve`.
6. After the Approval, source edits are allowed. Set up the test runner if one was agreed, and run the test command (with no tests yet, a "no tests ran" result is fine). If a machine line turns out wrong, correct it and get a new Approval now: setup is the last chance. Commit, then write the Breakdown with [spec.md](spec.md).
