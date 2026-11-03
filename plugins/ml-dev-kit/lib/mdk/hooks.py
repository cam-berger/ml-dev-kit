"""Hook bodies: refuse edits the Run's stage forbids, and turn the human's typed `approve` into an Approval."""
from __future__ import annotations

import re
from pathlib import Path

from .run import Run, RunError, active_run, is_approved, next_action, project_root, record_approval

APPROVE_RE = re.compile(r"^\s*approved?\s*[.!]?\s*$", re.IGNORECASE)

_FILE_KEY = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
_OWNED = "state.json and records.json belong to mdk: change Run state with an mdk command, not by editing them."


def gate(event: dict) -> dict | None:
    tool, given = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Bash":
        # Only commands that name Run files need the Run, so every other Bash call skips git entirely.
        command = given.get("command") or ""
        owned = "records.json" in command or ("docs/features" in command and "state.json" in command)
        return _deny(_OWNED) if owned and _active(event) else None
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
    parts = rel.parts
    if len(parts) == 4 and parts[:2] == ("docs", "features") and parts[3] in ("state.json", "records.json"):
        return _deny(_OWNED)
    if rel.as_posix() == "STANDARDS.md":
        return None if run.stage == "setup" else _deny(
            "STANDARDS.md is human-owned once setup is over: ask the human to edit it themselves."
        )
    if parts[:1] == ("docs",) or rel.as_posix() == "CONTEXT.md":
        return None
    if _source_edits_allowed(run):
        return None
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


def _active(event: dict) -> Run | None:
    if not event.get("cwd"):
        return None
    try:
        root = project_root(Path(event["cwd"]))
    except RunError:
        return None
    return active_run(root)


def _source_edits_allowed(run: Run) -> bool:
    if run.stage == "setup":
        return is_approved(run, "standards")
    return run.stage == "build" and is_approved(run, "spec", run.current)


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"ml-dev-kit: {reason}",
    }}
