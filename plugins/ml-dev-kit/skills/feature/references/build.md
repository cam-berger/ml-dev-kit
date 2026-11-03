# Build, review and Done

From `mdk begin` until Done or an Escalation, the human is out of the loop: the approved Spec is the only source of intent, and the Reviewer judges every Deviation against its Intent. In stage `escalated`, start at "Resolving an Escalation" below.

The packet for Feature `NN`: the Spec's path, `STANDARDS.md`, `CONTEXT.md` if it exists, and the base commit, which is `base` for `NN` under `features` in `mdk status`.

## Build

1. Dispatch `ml-dev-kit:implementer` with the packet. After an Escalation, also say what the human decided and what changed in the Spec. The code already written stays, and the implementer reads it with `git diff <base>`.
   - `Status: BLOCKED`: run `mdk escalate NN "<the blocker>"` and resolve it as below.
   - `DONE` or `DONE_WITH_CONCERNS`: go on. The Reviewer sees the concerns in the report.
2. Run `mdk check NN --timeout 540` with a Bash timeout of 600000, so that `mdk` stops a hung suite before Bash gives up. It prints `PASS` or `FAIL`, the problems, and the tail of the test output.
3. Dispatch `ml-dev-kit:reviewer` with the packet, the implementer's latest report, and the whole check output.
4. Route on the Reviewer's last line, `Verdict:`.
   - `CLEAN`, and the check printed `PASS`: finish the Feature (step 5).
   - `ESCALATE`, or any Deviation marked `ESCALATE`, even if the check printed `FAIL`: run `mdk escalate NN "<reason>"` and resolve it as below. A fix round cannot settle what only the human can decide. Write every Escalation reason so it stands on its own: a resumed Run sees only that text.
   - `FIX`, or the check printed `FAIL`: start a fix round. Send the Reviewer's findings and the check's problems to the implementer. Continue the same implementer if you can (SendMessage); otherwise dispatch a new one with the packet, the findings and its last report, so it can carry its lists forward. Handle its reply as in step 1, then repeat steps 2 to 4.
   - Fix rounds are capped at 3. If the third round still ends without `CLEAN` and `PASS`, run `mdk escalate NN "<the open findings>"`. Findings that survive three rounds need a decision, not another attempt.
5. Finish the Feature:
   - Append each Deviation the Reviewer passed under the Spec's `## Deviations` heading, as `- <deviation> — <the Reviewer's one-line reason>`. Touch nothing above that heading: it is the approved body, and Done checks it again. If a later round sends you back here, replace these lines rather than repeat them.
   - Append the implementer's last `Noticed:` list (it is cumulative) to `docs/features/<run-slug>/noticed.md`, one line each as `- NN: <item>`. Create the file the first time.
   - Run `mdk done NN --timeout 540` with a Bash timeout of 600000. It runs the check again and records Done only on `PASS`. On `FAIL`, treat it as a `FIX` verdict.
   - Commit the code with the Spec.
   - Tell the human in a few lines: what was built, the Deviations that passed, and what was noticed.
   - If `mdk done` printed `Run complete.`, end the Run: tell the human the work is on branch `mdk/<run-slug>`, that nothing was pushed, and summarise the Run (Features built, Deviations passed, the noticed list). Otherwise go on to the next Feature in [spec.md](spec.md).

Resuming in stage `build` without the implementer's report in this conversation: start at step 1 with a fresh fix-round count.

## Resolving an Escalation

The Feature waits for the human, because only the human changes what the Spec asks for.

1. Put it to the human: the reason (`escalation` in `mdk status`), what Build found, and the options.
2. The human decides. You amend the Spec body to match the decision, and change nothing else in it.
3. Dispatch `ml-dev-kit:spec-checker` on the amended Spec and bring its questions to the human, as in [spec.md](spec.md).
4. Run `mdk await spec NN` and ask for `approve`.
5. Commit, then run `mdk begin NN`. The base commit is kept, so the Reviewer still judges the whole Feature diff.
6. Go back to Build step 1. The fix-round count starts again from zero.
