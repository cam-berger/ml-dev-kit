"""The Run state machine: where Run files live and which transitions are legal.

Every other mdk module goes through here, so the model never edits state.json or
records.json itself and an Approval cannot be faked by writing a file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import docs

_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_STATE_KEYS = ("goal", "slug", "branch", "stage", "awaiting", "current", "features", "escalation")
_RECORDS_KEYS = ("approvals", "done")


class RunError(RuntimeError):
    """An illegal transition, or a Run that cannot be read."""


@dataclass
class Run:
    root: Path
    slug: str
    state: dict

    @property
    def dir(self) -> Path:
        return self.root / "docs" / "features" / self.slug

    @property
    def stage(self) -> str:
        return self.state["stage"]

    @property
    def awaiting(self) -> dict | None:
        return self.state["awaiting"]

    @property
    def current(self) -> str | None:
        return self.state["current"]

    @property
    def features(self) -> list[dict]:
        return self.state["features"]

    def feature(self, fid: str | None) -> dict:
        for feature in self.features:
            if feature["id"] == fid:
                return feature
        raise RunError(f"feature {fid} is not in this Run")

    def spec_path(self, fid: str) -> Path:
        return self.dir / f"{fid}-{self.feature(fid)['slug']}.md"


def project_root(start: Path) -> Path:
    return Path(_git(start, "rev-parse", "--show-toplevel"))


def has_runs(root: Path) -> bool:
    """Whether root holds a Run directory, readable or not: the sign that a broken hook must fail closed."""
    try:
        return bool(_state_files(root))
    except OSError:
        return False


def active_run(root: Path) -> Run | None:
    runs = []
    for path in _state_files(root):
        state = _load(path, _STATE_KEYS)
        if state["stage"] != "done":
            runs.append(Run(root, path.parent.name, state))
    if len(runs) > 1:
        raise RunError("more than one active Run: " + ", ".join(r.slug for r in runs))
    return runs[0] if runs else None


def init_run(root: Path, slug: str, goal: str) -> Run:
    if not _SLUG.fullmatch(slug):
        raise RunError(f"bad slug {slug!r}: use lowercase letters and digits, joined by single hyphens")
    existing = active_run(root)
    if existing:
        raise RunError(f"Run {existing.slug!r} is still active; finish it first")
    stage = "breakdown" if (root / "STANDARDS.md").exists() else "setup"
    run = Run(root, slug, {
        "goal": goal, "slug": slug, "branch": f"mdk/{slug}", "stage": stage, "awaiting": None,
        "current": None, "features": [], "escalation": None,
    })
    if run.dir.exists():
        raise RunError(f"{run.dir} already exists")
    if _git(root, "status", "--porcelain"):
        raise RunError("the working tree has uncommitted changes; commit or stash them first")
    _git(root, "switch", "-c", run.state["branch"])
    run.dir.mkdir(parents=True)
    _save_records(run, {"approvals": [], "done": []})
    _save_state(run)
    return run


def current_hash(run: Run, kind: str, fid: str | None = None) -> str | None:
    path = _document(run, kind, fid)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return docs.spec_body_hash(text) if kind == "spec" else docs.text_hash(text)


def is_approved(run: Run, kind: str, fid: str | None = None) -> bool:
    current = current_hash(run, kind, fid)
    if current is None:
        return False
    feature = fid if kind == "spec" else None
    approvals = [a for a in _records(run)["approvals"] if a["kind"] == kind and a["feature"] == feature]
    return bool(approvals) and approvals[-1]["sha256"] == current


def request_approval(run: Run, kind: str, fid: str | None = None) -> None:
    if kind == "standards":
        _prepare_standards(run)
    elif kind == "breakdown":
        _prepare_breakdown(run)
    elif kind == "spec":
        _prepare_spec(run, fid)
    else:
        raise _unknown_kind(kind)
    run.state["awaiting"] = {"kind": kind, "feature": fid if kind == "spec" else None}
    _save_state(run)


def record_approval(run: Run) -> dict | None:
    waiting = run.awaiting
    if waiting is None:
        return None
    sha = current_hash(run, waiting["kind"], waiting["feature"])
    if sha is None:
        raise RunError(f"cannot record the Approval: the {waiting['kind']} document is missing")
    record = {"kind": waiting["kind"], "feature": waiting["feature"], "sha256": sha, "at": _now()}
    records = _records(run)
    records["approvals"].append(record)
    _save_records(run, records)
    run.state["awaiting"] = None
    _save_state(run)
    return record


def begin_build(run: Run, fid: str) -> None:
    feature = run.feature(fid)
    if feature["status"] not in ("pending", "escalated"):
        raise RunError(f"feature {fid} is {feature['status']}, so it cannot begin")
    if not is_approved(run, "spec", fid):
        raise RunError(f"the Spec for feature {fid} is not approved")
    if (run.stage, run.current, run.awaiting) != ("spec", fid, None):
        raise RunError(f"run mdk await spec {fid} and wait for the human's fresh Approval before building")
    spec = run.spec_path(fid).relative_to(run.root).as_posix()
    if _git(run.root, "status", "--porcelain", "--", spec):
        raise RunError(f"commit {spec} first: the Spec must be committed before Build")
    if feature["base"] is None:
        feature["base"] = _git(run.root, "rev-parse", "HEAD")
    feature["status"] = "building"
    run.state.update(stage="build", current=fid, escalation=None)
    _save_state(run)


def escalate(run: Run, fid: str, reason: str) -> None:
    feature = run.feature(fid)
    if feature["status"] != "building":
        raise RunError(f"feature {fid} is {feature['status']}; only a building feature can escalate")
    feature["status"] = "escalated"
    run.state.update(stage="escalated", escalation={"feature": fid, "reason": reason, "at": _now()})
    _save_state(run)


def mark_done(run: Run, fid: str) -> None:
    if run.stage != "build" or run.current != fid:
        raise RunError(f"feature {fid} is not being built (stage {run.stage}, current {run.current})")
    if not is_approved(run, "spec", fid):
        raise RunError(
            f"the Spec body for feature {fid} changed after its Approval; "
            f"run mdk escalate {fid} with the reason, so the human can approve the change"
        )
    spec = _read(run.spec_path(fid))
    records = _records(run)
    # The whole Spec, not just its body: by Done the Deviations are filled in.
    records["done"].append({"feature": fid, "sha256": docs.text_hash(spec), "at": _now()})
    _save_records(run, records)
    run.feature(fid)["status"] = "done"
    upcoming = _first_unfinished(run)
    run.state.update(stage="spec" if upcoming else "done", current=upcoming)
    _save_state(run)


def next_action(run: Run) -> str:
    waiting, fid = run.awaiting, run.current
    if waiting:
        subject = {"standards": "STANDARDS.md", "breakdown": "the breakdown"}.get(
            waiting["kind"], f"the Spec for feature {waiting['feature']}"
        )
        return f"Waiting for the human to approve {subject}; their whole reply must be 'approve'."
    if run.stage == "setup":
        if is_approved(run, "standards"):
            return (
                "STANDARDS.md is approved: write breakdown.md with the human, "
                "then run mdk await breakdown."
            )
        return "Write STANDARDS.md with the human, then run mdk await standards."
    if run.stage == "breakdown":
        if not is_approved(run, "breakdown"):
            return "Write breakdown.md with the human, then run mdk await breakdown."
        first = _first_unfinished(run)
        return (
            f"The breakdown is approved: write the Spec for feature {first} with the human, "
            f"then run mdk await spec {first}."
        )
    if run.stage == "spec":
        if is_approved(run, "spec", fid):
            return f"The Spec for feature {fid} is approved: commit it, then run mdk begin {fid}."
        return f"Write the Spec for feature {fid} with the human, then run mdk await spec {fid}."
    if run.stage == "build":
        return (
            f"Build feature {fid}, then run mdk done {fid}; "
            f"if the Spec cannot be met, run mdk escalate {fid} with the reason."
        )
    if run.stage == "escalated":
        why = run.state["escalation"]
        return (
            f"Feature {why['feature']} is escalated ({why['reason']}): put it to the human, "
            f"revise the Spec, then run mdk await spec {why['feature']}."
        )
    return "Run complete."


def _prepare_standards(run: Run) -> None:
    if run.stage != "setup":
        raise RunError(f"STANDARDS.md is approved during setup, but this Run is in stage {run.stage}")
    docs.parse_standards(_read(run.root / "STANDARDS.md"))


def _prepare_breakdown(run: Run) -> None:
    if not (run.stage == "breakdown" or (run.stage == "setup" and is_approved(run, "standards"))):
        raise RunError("the breakdown comes after an approved STANDARDS.md")
    planned = docs.parse_breakdown(_read(run.dir / "breakdown.md"))
    if any(f["status"] != "pending" for f in run.features):
        raise RunError("the breakdown can no longer change: a feature has already started")
    run.state["features"] = [
        {"id": p.id, "slug": p.slug, "status": "pending", "base": None} for p in planned
    ]
    run.state["stage"] = "breakdown"


def _prepare_spec(run: Run, fid: str | None) -> None:
    if fid is None:
        raise RunError("a Spec Approval needs a feature ID")
    if not is_approved(run, "breakdown"):
        raise RunError("the breakdown is not approved yet")
    status = run.feature(fid)["status"]
    if status not in ("pending", "escalated"):
        raise RunError(f"feature {fid} is {status}; only a pending or escalated feature can be approved")
    first = _first_unfinished(run)
    if first != fid:
        blocker = run.feature(first)["status"]
        raise RunError(f"feature {first} is {blocker} and must be done before feature {fid}")
    problems = docs.spec_problems(_read(run.spec_path(fid)), fid)
    if problems:
        raise RunError(f"the Spec for feature {fid} is not ready:\n- " + "\n- ".join(problems))
    run.state.update(stage="spec", current=fid)


def _first_unfinished(run: Run) -> str | None:
    return next((f["id"] for f in run.features if f["status"] != "done"), None)


def _document(run: Run, kind: str, fid: str | None) -> Path:
    if kind == "standards":
        return run.root / "STANDARDS.md"
    if kind == "breakdown":
        return run.dir / "breakdown.md"
    if kind == "spec":
        if fid is None:
            raise RunError("a Spec Approval needs a feature ID")
        return run.spec_path(fid)
    raise _unknown_kind(kind)


def _unknown_kind(kind: str) -> RunError:
    return RunError(f"unknown Approval kind {kind!r}; expected standards, breakdown or spec")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git(cwd: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as err:
        raise RunError(f"cannot run git: {err}") from err
    if done.returncode != 0:
        raise RunError(done.stderr.strip() or f"git {args[0]} failed")
    return done.stdout.strip()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        raise RunError(f"cannot read {path}: {err.strerror}") from err


def _state_files(root: Path) -> list[Path]:
    # init writes both files, so a state.json without records.json belongs to some other tool.
    found = sorted((root / "docs" / "features").glob("*/state.json"))
    return [path for path in found if (path.parent / "records.json").is_file()]


def _load(path: Path, keys: tuple[str, ...]) -> dict:
    try:
        data = json.loads(_read(path))
    except ValueError as err:
        raise RunError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict) or any(key not in data for key in keys):
        raise RunError(f"{path} is not an mdk Run file: it needs the keys {', '.join(keys)}")
    return data


def _records(run: Run) -> dict:
    return _load(run.dir / "records.json", _RECORDS_KEYS)


def _save_records(run: Run, records: dict) -> None:
    _save_json(run.dir / "records.json", records)


def _save_state(run: Run) -> None:
    _save_json(run.dir / "state.json", run.state)


def _save_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
