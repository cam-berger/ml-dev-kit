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


@dataclass
class _Suite:
    problems: list[str]
    output: str
    finished: bool


def check_feature(run: Run, fid: str, timeout: int = 1800) -> CheckResult:
    problems: list[str] = []
    tail = ""
    if not is_approved(run, "spec", fid):
        problems.append(f"Spec {fid} has no current Approval")
    ids = _behaviour_ids(run, fid)
    if ids == []:
        problems.append(f"Spec {fid} lists no Behaviour IDs, so no test can show it was built")
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
        problems += [f"no test names {i}" for i in ids or [] if not any(docs.mentions_id(t, i) for t in tests)]
        suite = _run_suite(standards.test_command, run.root, timeout)
        problems += suite.problems
        if suite.finished:
            # A named test that never ran proves nothing, and a green suite can run zero tests.
            problems += [
                f"test output never names {i} (did it run?)" for i in ids or [] if not docs.mentions_id(suite.output, i)
            ]
        tail = "\n".join(suite.output.splitlines()[-TAIL_LINES:])
    return CheckResult(not problems, problems, tail)


def _behaviour_ids(run: Run, fid: str) -> list[str] | None:
    try:
        spec = run.spec_path(fid).read_text(encoding="utf-8")
    except OSError:
        return None  # the missing Spec is already reported as having no Approval
    return docs.behaviour_ids(spec)


def standards_test_files(run: Run) -> dict[str, list[str]]:
    """Each Test files glob in STANDARDS.md with the files it matches, as the Done check will see them."""
    standards = docs.parse_standards((run.root / "STANDARDS.md").read_text(encoding="utf-8"))
    return glob_matches(run.root, standards.test_globs)


def glob_matches(root: Path, globs: tuple[str, ...]) -> dict[str, list[str]]:
    """The one glob matcher: Setup shows its result, and Done reads the files it finds."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True,
    ).stdout.split("\0")
    paths = [path for path in dict.fromkeys(listed) if path]
    return {glob: [path for path in paths if docs.glob_to_regex(glob).fullmatch(path)] for glob in globs}


def _test_texts(root: Path, globs: tuple[str, ...]) -> list[str]:
    texts = []
    for path in dict.fromkeys(p for matched in glob_matches(root, globs).values() for p in matched):
        try:
            texts.append((root / path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue  # listed by git but gone or unreadable: it names no tests
    return texts


def _run_suite(command: str, root: Path, timeout: int) -> _Suite:
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, errors="replace", start_new_session=True,
        )
    except OSError as err:
        return _Suite([f"test command could not start: {err.strerror}"], "", False)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            out, err = proc.communicate(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired as late:
            out, err = late.stdout, late.stderr
        return _Suite([f"test command timed out after {timeout}s"], _joined(out, err), False)
    failed = [f"test command failed (exit {proc.returncode})"] if proc.returncode else []
    return _Suite(failed, _joined(out, err), True)


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the shell and everything it started: a compound command leaves children behind it."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        proc.kill()


def _joined(*streams: str | bytes | None) -> str:
    lines = []
    for stream in streams:
        text = stream.decode("utf-8", errors="replace") if isinstance(stream, bytes) else stream or ""
        lines += text.splitlines()
    return "\n".join(lines)
