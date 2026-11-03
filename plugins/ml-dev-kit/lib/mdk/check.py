"""The mechanical Done check: the part of 'done' that the agent cannot talk its way past."""
from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import docs
from .run import Run, is_approved

TAIL_LINES = 40
KILL_GRACE = 5


@dataclass
class CheckResult:
    passed: bool
    problems: list[str]
    output_tail: str


def check_feature(run: Run, fid: str, timeout: int = 1800) -> CheckResult:
    problems: list[str] = []
    tail = ""
    if not is_approved(run, "spec", fid):
        problems.append(f"Spec {fid} has no current Approval")
    try:
        standards = docs.parse_standards((run.root / "STANDARDS.md").read_text(encoding="utf-8"))
    except OSError as err:
        problems.append(f"cannot read STANDARDS.md: {err.strerror}")
    except docs.DocError as err:
        problems.append(str(err))
    else:
        tests = _test_texts(run.root, standards.test_globs)
        if not tests:
            problems.append("no test files match " + ", ".join(standards.test_globs))
        problems += [f"no test names {i}" for i in _uncovered(run, fid, tests)]
        more, tail = _run_suite(standards.test_command, run.root, timeout)
        problems += more
    return CheckResult(not problems, problems, tail)


def _test_texts(root: Path, globs: tuple[str, ...]) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True,
    ).stdout.split("\0")
    patterns = [docs.glob_to_regex(g) for g in globs]
    texts = []
    for path in dict.fromkeys(listed):
        if path and any(p.fullmatch(path) for p in patterns):
            try:
                texts.append((root / path).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue  # listed by git but gone or unreadable: it names no tests
    return texts


def _uncovered(run: Run, fid: str, tests: list[str]) -> list[str]:
    try:
        spec = run.spec_path(fid).read_text(encoding="utf-8")
    except OSError:
        return []  # the missing Spec is already reported as having no Approval
    return [i for i in docs.behaviour_ids(spec) if not any(docs.mentions_id(t, i) for t in tests)]


def _run_suite(command: str, root: Path, timeout: int) -> tuple[list[str], str]:
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", start_new_session=True,
        )
    except OSError as err:
        return [f"test command could not start: {err.strerror}"], ""
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            out, err = proc.communicate(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired as late:
            out, err = late.stdout, late.stderr
        return [f"test command timed out after {timeout}s"], _tail(out, err)
    failed = [f"test command failed (exit {proc.returncode})"] if proc.returncode else []
    return failed, _tail(out, err)


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the shell and everything it started: a compound command leaves children behind it."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        proc.kill()


def _tail(*streams: str | bytes | None) -> str:
    lines = []
    for stream in streams:
        text = stream.decode("utf-8", errors="replace") if isinstance(stream, bytes) else stream or ""
        lines += text.splitlines()
    return "\n".join(lines[-TAIL_LINES:])
