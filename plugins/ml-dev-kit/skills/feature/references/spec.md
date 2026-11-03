# Breakdown and Specs

The human is in the loop for all of this. A Spec's Approval is the last human gate before Build, so every gap a Spec leaves becomes a guess that Build makes unseen.

## How to grill

- Settle the decisions that others depend on first, then the ones that hang off them.
- If the human says something the code contradicts, show both and ask which is right.
- Test answers against concrete scenarios, especially edge cases, so the boundaries are explicit.
- When a term is vague or clashes with `CONTEXT.md`, propose one precise term. Write each settled term into `CONTEXT.md` straight away, under `## Language`: `**Term**:`, a one-sentence definition, then `_Avoid_:` and the words not to use. Domain terms only, no implementation details. Create the file when the first term settles.
- Add an ADR only when a decision is hard to reverse, surprising without context, and a real trade-off. Write it to `docs/adr/NNNN-<slug>.md`, numbered after the highest existing one: a title and a short paragraph giving the context, the decision and why.

## Breakdown

1. Grill on the Goal's objective first: who it is for, what changes for them, and what is out. Details come later, per Feature.
2. Propose how the Goal splits into Features, in build order. Each Feature must be specifiable, buildable and testable on its own. A small Goal is one Feature, and its Breakdown is one line.
3. Write `docs/features/<run-slug>/breakdown.md` from [../templates/breakdown.md](../templates/breakdown.md).
4. Run `mdk await breakdown`, which prints the Features it read. The Run builds exactly that list, so check it against what you agreed, then ask for `approve` and commit.

Between Features (stage `spec`) the Breakdown may change again with the human: rewrite it, keeping each started or Done Feature's line as it is, and repeat step 4.

## Each Feature

Take the Feature that `next` names: the first in the Breakdown that is not Done.

1. Grill on this Feature: its Intent, its Behaviours as observable outcomes, its public interface and where the tests attach, and what is out of scope. The Reviewer judges every Deviation against the Intent, so a vague Intent turns each gap into an Escalation.
2. Write `docs/features/<run-slug>/NN-<feature-slug>.md` from [../templates/spec.md](../templates/spec.md), with `NN` and the slug from the Breakdown. Number Behaviours `NN-B1`, `NN-B2` and so on. Its length should match the size of the Feature.
3. Dispatch `ml-dev-kit:spec-checker` with the Spec's path. If it replies `nothing important left`, go on. Otherwise put the questions that matter to the human, with the checker's recommendation, and update the Spec with each answer.
4. Run `mdk await spec NN` and ask for `approve`.
5. Commit the Spec, run `mdk begin NN`, and continue in [build.md](build.md).
