"""Hook bodies: refuse edits the Run's stage forbids, and turn the human's typed `approve` into an Approval."""
from __future__ import annotations

import re
from pathlib import Path

from .run import Run, RunError, active_run, has_runs, is_approved, next_action, project_root, record_approval

APPROVE_RE = re.compile(r"^\s*approved?\s*[.!]?\s*$", re.IGNORECASE)

_FILE_KEY = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
_OWNED = "state.json and records.json belong to mdk: change Run state with an mdk command, not by editing them."
_HOOK_CALL = re.compile(r"\bmdk\b[^\n|;&]*\bhook['\"]?\s+['\"]?(?:gate|prompt)\b")
_HOOK_ONLY = "`mdk hook` is for Claude Code's hooks: only the human's own typed reply records an Approval."
_NO_WORKAROUND = (
    "Don't get around this another way (Bash, sed, cat, a script); "
    "the gate is what keeps the human in charge of the Run."
)
_ALWAYS_ALLOWED = (("docs", "features"), ("docs", "adr"))


def gate(event: dict) -> dict | None:
    tool, given = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Bash":
        # Only commands that name Run files or mdk's hook need the Run, so every other Bash call skips git entirely.
        reason = _bash_reason(given.get("command") or "")
        return _deny(reason) if reason and _active(event) else None
    key = _FILE_KEY.get(tool)
    if key is None or not given.get(key):
        return None
    run = _active(event)
    if run is None:
        return None
    try:
        rel = (Path(event["cwd"]) / given[key]).resolve().relative_to(run.root.resolve())
    except ValueError:
        return None
    # macOS and Windows ignore case, so the deny rules match every spelling and the allow rules only the exact one.
    folded = tuple(part.casefold() for part in rel.parts)
    if len(folded) == 4 and folded[:2] == ("docs", "features") and folded[3] in ("state.json", "records.json"):
        return _deny(_OWNED)
    if folded == ("standards.md",) and run.stage != "setup":
        return _deny("STANDARDS.md is human-owned once setup is over: ask the human to edit it themselves.")
    if rel.parts in (("STANDARDS.md",), ("CONTEXT.md",)) or rel.parts[:2] in _ALWAYS_ALLOWED:
        return None
    if _source_edits_allowed(run):
        return None
    if run.stage == "build":
        return _deny(
            f"the Spec for feature {run.current} is missing or its body changed after its Approval. "
            f"Restore the approved Spec body, or run `mdk escalate {run.current} <reason>` "
            "so the human can approve the change."
        )
    return _deny(f"source edits are not allowed yet. {next_action(run)}")


def on_prompt(event: dict) -> dict | None:
    if not APPROVE_RE.match(event.get("prompt") or ""):
        return None
    run = _active(event)
    record = record_approval(run) if run else None
    if record is None:
        return None
    subject = f"{record['kind']} {record['feature']}" if record["feature"] else record["kind"]
    return {"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": f"ml-dev-kit: recorded the human's Approval of {subject} (sha256 {record['sha256'][:12]})",
    }}


def fails_closed(event: object) -> bool:
    """Whether a gate that cannot decide must deny: only inside a project that has Runs."""
    cwd = event.get("cwd") if isinstance(event, dict) else None
    start = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    try:
        return (project_root(start) / "docs" / "features").is_dir()
    except RunError:
        return _run_above(start)


def _active(event: dict) -> Run | None:
    if not event.get("cwd"):
        return None
    cwd = Path(event["cwd"])
    try:
        root = project_root(cwd)
    except RunError as err:
        if _run_above(cwd):
            raise RunError(f"{err} (a Run lives here, so the gate denies until git works)") from err
        return None
    return active_run(root)


def _run_above(start: Path) -> bool:
    """Without git there is no project root, so look for a Run in this folder and every folder above it."""
    return any(has_runs(folder) for folder in (start, *start.parents))


def _bash_reason(command: str) -> str | None:
    if "records.json" in command or ("docs/features" in command and "state.json" in command):
        return _OWNED
    if _HOOK_CALL.search(command):
        return _HOOK_ONLY
    return None


def _source_edits_allowed(run: Run) -> bool:
    if run.stage == "setup":
        return is_approved(run, "standards")
    return run.stage == "build" and is_approved(run, "spec", run.current)


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"ml-dev-kit: {reason} {_NO_WORKAROUND}",
    }}
