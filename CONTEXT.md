# Feature Workflow Plugin

A Claude Code plugin that takes one Goal per Run through human-approved specification, architecture-first implementation, and testing, so the resulting codebase stays explainable and easy to build on.

## Language

**Run**:
One invocation of the plugin, carrying exactly one Goal from start to finish.
_Avoid_: session, job, pipeline

**Goal**:
What the human asks for in a Run; either a single Feature or something larger that splits into several.
_Avoid_: epic, request, task

**Feature**:
The smallest unit of work that is specified, built, and tested on its own.
_Avoid_: story, ticket, item

**Stage**:
One of the three phases every Feature passes through in order: Spec, Build, Test.
_Avoid_: phase, step

**Breakdown**:
The human-approved list of Features a Goal splits into, in build order.
_Avoid_: plan, roadmap, backlog

**Spec**:
The written description of one Feature, produced by grilling the human, that Build works from.
_Avoid_: requirements, PRD, design doc

**Approval**:
The human's explicit yes that unlocks the next Stage; nothing moves forward without one.
_Avoid_: sign-off, review, confirmation

**Intent**:
The stated why behind a Feature, written into its Spec, that every later decision is judged against.
_Avoid_: purpose, motivation, rationale

**Deviation**:
Anything Build or Test does that the approved Spec does not say, including filling a gap the Spec left open.
_Avoid_: change, drift, exception

**Reviewer**:
The agent that judges each Deviation against the Feature's Intent and scope.
_Avoid_: checker, validator, critic

**Escalation**:
A Deviation the Reviewer sends back to the human because it changes scope or cannot be traced to the Intent.
_Avoid_: blocker, flag, interrupt

**Done**:
A Feature whose every Spec behaviour has a test written before its code, and whose project test suite has no failures beyond the Baseline.
_Avoid_: complete, finished, shipped

**Baseline**:
The set of test failures that already existed in a project when the plugin was set up, recorded and shown to the human.
_Avoid_: known failures, allowlist, skip list

**Standards**:
A project's written rules for architecture, documentation, and testing, set by the human from the plugin's defaults.
_Avoid_: conventions, guidelines, style guide

## Relationships

- A **Run** carries exactly one **Goal**
- A **Goal** splits into one or more **Features**; a small Goal is exactly one Feature
- Each **Feature** passes through every **Stage** in order before the next **Feature** starts
- The human co-writes the **Breakdown** and each **Spec**; each needs an **Approval**
- A **Spec**'s **Approval** is the last human gate before Build; Build and Test then run without the human
- Every **Spec** states its **Intent**
- The **Reviewer** passes a **Deviation** only if it traces to the **Intent** and does not materially change scope; any other Deviation becomes an **Escalation**
- A passed **Deviation** is recorded in the **Spec** so the Spec stays a true record of what was built
- An **Escalation** pauses that **Feature** until the human resolves it and gives a new **Approval**
- The next **Feature** starts only when the current one is **Done**
- A failing test that Build cannot fix within the **Spec** becomes an **Escalation**
- Each project has exactly one **Standards**, written with the human on the first **Run** in that project
- Build follows the **Standards** and the **Reviewer** enforces them; only the human changes them
- A **Run** starts with one command given the **Goal**; its **Breakdown**, **Specs**, and progress are saved in the project so a paused Run resumes where it stopped
- The plugin works on new and existing projects; in an existing project the first **Run** also surveys current code against the **Standards**
- Build reshapes only existing code the **Feature** touches; problems found elsewhere are reported to the human, not fixed

## Example dialogue

> **Dev:** "The **Goal** is 'add user accounts' — is that one **Feature**?"
> **Human:** "No, that splits into sign-up, login, and password reset. Each one goes through Spec, Build, and Test before the next starts."

> **Dev:** "Build found locked-out accounts need a different response. The **Spec** is silent."
> **Reviewer:** "The **Intent** is 'users can securely sign in', so this is within it and adds no scope. Passed, recorded as a **Deviation**."
> **Dev:** "Build also wants to add 'remember me'."
> **Reviewer:** "That's new scope. **Escalation**: the human decides."

## Flagged ambiguities

- "one goal or feature per run" — resolved: a **Run** always has one **Goal**; the Goal may be a single **Feature** or split into several.
