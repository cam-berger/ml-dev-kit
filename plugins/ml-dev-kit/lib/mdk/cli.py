"""The mdk command line: argument parsing, exit codes and hook I/O. The rules live in run, check and hooks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import hooks
from .check import CheckResult, check_feature, standards_test_files
from .docs import DocError
from .run import (
    Run, RunError, active_run, begin_build, escalate, init_run, mark_done, next_action, planned_features,
    project_root, request_approval,
)

_STATUS_KEYS = ("goal", "branch", "stage", "awaiting", "current", "features", "escalation")
_SHOWN_FILES = 10


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except (RunError, DocError) as err:
        print(f"mdk: {err}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdk", description="Change ml-dev-kit Run state; the only way to do it.")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("slug")
    init.add_argument("goal", nargs="+")
    commands.add_parser("status")
    wait = commands.add_parser("await")
    wait.add_argument("kind", choices=["standards", "breakdown", "spec"])
    wait.add_argument("fid", nargs="?", metavar="NN")
    commands.add_parser("begin").add_argument("fid", metavar="NN")
    for name in ("check", "done"):
        timed = commands.add_parser(name)
        timed.add_argument("fid", metavar="NN")
        timed.add_argument("--timeout", type=int, default=1800, metavar="S")
    esc = commands.add_parser("escalate")
    esc.add_argument("fid", metavar="NN")
    esc.add_argument("reason", nargs="+")
    commands.add_parser("hook").add_argument("event", choices=["gate", "prompt"])
    return parser


def _run() -> Run:
    run = active_run(project_root(Path.cwd()))
    if run is None:
        raise RunError("no active Run; start one with mdk init <slug> <goal>")
    return run


def _next(run: Run) -> int:
    print(next_action(run))
    return 0


def _init(args: argparse.Namespace) -> int:
    run = init_run(project_root(Path.cwd()), args.slug, " ".join(args.goal))
    print(f"Started Run {run.slug} on branch {run.state['branch']}.")
    return _next(run)


def _status(args: argparse.Namespace) -> int:
    run = active_run(project_root(Path.cwd()))
    shown = {"active": False} if run is None else {
        "active": True, "slug": run.slug, **{k: run.state[k] for k in _STATUS_KEYS}, "next": next_action(run),
    }
    print(json.dumps(shown, indent=2))
    return 0


def _await(args: argparse.Namespace) -> int:
    run = _run()
    request_approval(run, args.kind, args.fid or (run.current if args.kind == "spec" else None))
    if args.kind == "breakdown":
        print("Features in build order:")
        for feature in planned_features(run):
            status = "" if feature["status"] == "pending" else f" ({feature['status']})"
            print(f"- {feature['id']}. {feature['slug']}{status}")
    elif args.kind == "standards":
        print("Files the Done check searches for test names:")
        for glob, files in standards_test_files(run).items():
            print(f"- `{glob}`: {_file_list(files)}")
    return _next(run)


def _file_list(files: list[str]) -> str:
    if not files:
        return (
            "no files. Fine while the project has no tests; otherwise fix it. "
            "A glob needs a wildcard to match files: `tests/**/*.py`, not `tests`."
        )
    more = len(files) - _SHOWN_FILES
    return ", ".join(files[:_SHOWN_FILES]) + (f" and {more} more" if more > 0 else "")


def _begin(args: argparse.Namespace) -> int:
    run = _run()
    begin_build(run, args.fid)
    return _next(run)


def _check(args: argparse.Namespace) -> int:
    result = check_feature(_run(), args.fid, args.timeout)
    _report(result)
    return 0 if result.passed else 1


def _done(args: argparse.Namespace) -> int:
    run = _run()
    result = check_feature(run, args.fid, args.timeout)
    _report(result)
    if not result.passed:
        return 1
    mark_done(run, args.fid)
    return _next(run)


def _escalate(args: argparse.Namespace) -> int:
    run = _run()
    escalate(run, args.fid, " ".join(args.reason))
    return _next(run)


def _report(result: CheckResult) -> None:
    print("PASS" if result.passed else "FAIL")
    for problem in result.problems:
        print(f"- {problem}")
    if result.output_tail:
        print("--- test output (tail) ---")
        print(result.output_tail)


def _hook(args: argparse.Namespace) -> int:
    return _gate() if args.event == "gate" else _prompt()


def _gate() -> int:
    event: object = None
    try:
        event = json.load(sys.stdin)
        return _emit(hooks.gate(event))
    except Exception as err:  # a broken gate must not wave edits through inside a project that has Runs
        if not hooks.fails_closed(event):
            return 0
        print(f"ml-dev-kit: hook error: {err}", file=sys.stderr)
        return 2


def _prompt() -> int:
    try:
        return _emit(hooks.on_prompt(json.load(sys.stdin)))
    except Exception as err:  # never block the human's message
        print(f"ml-dev-kit: warning: prompt hook skipped: {err}", file=sys.stderr)
        return 0


def _emit(result: dict | None) -> int:
    if result is not None:
        print(json.dumps(result))
    return 0


_COMMANDS = {
    "init": _init, "status": _status, "await": _await, "begin": _begin, "check": _check,
    "done": _done, "escalate": _escalate, "hook": _hook,
}
