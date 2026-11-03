"""Shared test fixtures. Importing this module makes `import mdk` work."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mdk.run import Run

PLUGIN = Path(__file__).resolve().parent.parent
REPO = PLUGIN.parent.parent

if str(PLUGIN / "lib") not in sys.path:
    sys.path.insert(0, str(PLUGIN / "lib"))

STANDARDS_OK = """\
# Standards

## Testing

Test command: `python3 -m unittest discover -s tests`
Test files: `tests/**/*.py`
"""

BREAKDOWN_OK = """\
01. sign-up — New users create an account.
02. login — Users sign in.
"""


def spec_text(fid: str = "01", behaviours: tuple[str, ...] = ("B1", "B2")) -> str:
    """A valid Spec. Deviations stays last and empty, as at Approval."""
    ids = "".join(
        f"- **{fid}-{b}** — {b} gives the user a result they can observe.\n"
        for b in behaviours
    )
    return (
        f"# Feature {fid}\n\n"
        "## Intent\nUsers can do the thing, so that they do not have to do it by hand.\n\n"
        f"## Behaviours\n{ids}\n"
        "## Interface and seams\nOne entry point; storage is behind a small interface.\n\n"
        "## Out of scope\nAnything not listed under Behaviours.\n\n"
        "## Deviations\n"
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def write(root: Path, rel: str, text: str) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def commit(root: Path, msg: str) -> None:
    # --allow-empty so make_repo works with no files and tests can commit "nothing changed".
    _git(root, "add", "-A")
    _git(root, "commit", "--allow-empty", "-m", msg)


def make_repo(tmp: Path, files: dict[str, str] | None = None) -> Path:
    """A fresh repo on `main` with one commit. Config is local so the user's global git config is irrelevant."""
    root = Path(tmp)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "commit.gpgsign", "false")
    for rel, text in (files or {}).items():
        write(root, rel, text)
    commit(root, "init")
    return root


def build_ready_repo(tmp: Path, test_command: str) -> tuple[Path, Run]:
    """A one-feature Run driven, via the real transitions, to `begin_build("01")`."""
    from mdk.run import begin_build, init_run, record_approval, request_approval

    standards = f"# Standards\n\nTest command: `{test_command}`\nTest files: `tests/**/*.py`\n"
    root = make_repo(tmp, {"STANDARDS.md": standards})
    run = init_run(root, "accounts", "Let people sign up")
    write(root, "docs/features/accounts/breakdown.md", "01. sign-up — New users create an account.\n")
    request_approval(run, "breakdown")
    record_approval(run)
    run.spec_path("01").write_text(spec_text("01"), encoding="utf-8")
    request_approval(run, "spec", "01")
    record_approval(run)
    commit(root, "spec 01")
    begin_build(run, "01")
    return root, run
