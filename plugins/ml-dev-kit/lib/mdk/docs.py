"""Parse and hash the Markdown documents of a Run (Spec, Breakdown, STANDARDS.md).

Pure and I/O-free, so that every other mdk module can trust one reading of these files.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

SPEC_SECTIONS = ("Intent", "Behaviours", "Interface and seams", "Out of scope", "Deviations")

_BEFORE = r"(?<![0-9A-Za-z])"
_AFTER = r"(?![0-9])"
_BEHAVIOUR_ID = re.compile(_BEFORE + r"(\d{2})-B(\d+)" + _AFTER)
_LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s")
_BREAKDOWN_LINE = re.compile(r"^(\d{2})\. ([a-z0-9]+(?:-[a-z0-9]+)*) [—-] (.+)$")
_TEST_COMMAND = re.compile(r"^Test command:\s*`([^`]+)`\s*$")
_TEST_FILES = re.compile(r"^Test files:\s*(.+)$")
_GLOB_TOKENS = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}


class DocError(ValueError):
    """A Run document is malformed."""


@dataclass(frozen=True)
class PlannedFeature:
    id: str
    slug: str
    summary: str


@dataclass(frozen=True)
class Standards:
    test_command: str
    test_globs: tuple[str, ...]


def _lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").rstrip().split("\n")]


def _first_match(pattern: re.Pattern[str], lines: list[str]) -> re.Match[str] | None:
    return next(filter(None, map(pattern.match, lines)), None)


def _sha256(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).rstrip().encode("utf-8")).hexdigest()


def _heading(line: str) -> str | None:
    """The name of a `## ` section heading. Every reading of the sections goes through here, so they agree."""
    return line[3:].strip() if line.startswith("## ") else None


def _section_names(lines: list[str]) -> list[str]:
    return [name for name in map(_heading, lines) if name is not None]


def _section(lines: list[str], name: str) -> list[str]:
    found, inside = [], False
    for line in lines:
        heading = _heading(line)
        if heading is not None:
            inside = heading == name
        elif inside:
            found.append(line)
    return found


def behaviour_ids(text: str) -> list[str]:
    found = [m.group(0) for line in _section(_lines(text), "Behaviours") for m in _BEHAVIOUR_ID.finditer(line)]
    return list(dict.fromkeys(found))


def spec_problems(text: str, feature_id: str) -> list[str]:
    lines = _lines(text)
    names = _section_names(lines)
    problems = [f"missing section: ## {s}" for s in SPEC_SECTIONS if s not in names]
    in_spec = [n for n in names if n in SPEC_SECTIONS]
    if "Deviations" in names and names[-1] != "Deviations":
        problems.append("## Deviations must be the last section")
    elif in_spec != [s for s in SPEC_SECTIONS if s in in_spec]:
        order = ", ".join(SPEC_SECTIONS)
        problems.append(f"sections must appear once each, in this order: {order}")
    ids = behaviour_ids(text)
    if not ids:
        problems.append(f"## Behaviours has no behaviour IDs such as {feature_id}-B1")
    prefix = feature_id + "-"
    problems += [f"behaviour {i} must start with {prefix}" for i in ids if not i.startswith(prefix)]
    return problems + _behaviour_line_problems(_section(lines, "Behaviours"), feature_id)


def _behaviour_line_problems(section: list[str], feature_id: str) -> list[str]:
    # A top-level list item is one Behaviour, and its first ID is its own; indented items detail the one above.
    problems, own = [], []
    for item in filter(_LIST_ITEM.match, section):
        found = _BEHAVIOUR_ID.search(item)
        if found:
            own.append(found.group(0))
        else:
            problems.append(f"this Behaviours line has no ID such as {feature_id}-B1: {item}")
    repeated = dict.fromkeys(i for i in own if own.count(i) > 1)
    return problems + [f"behaviour ID {i} is used by more than one line" for i in repeated]


def spec_body_hash(text: str) -> str:
    lines = _lines(text)
    cut = next((n for n, line in enumerate(lines) if _heading(line) == "Deviations"), len(lines))
    return _sha256(lines[:cut])


def text_hash(text: str) -> str:
    return _sha256(_lines(text))


def parse_breakdown(text: str) -> list[PlannedFeature]:
    matches = (_BREAKDOWN_LINE.match(line) for line in _lines(text))
    features = [PlannedFeature(*m.groups()) for m in matches if m]
    if not features:
        raise DocError("breakdown lists no features; expected lines like '01. slug — summary'")
    expected = [f"{n:02d}" for n in range(1, len(features) + 1)]
    if [f.id for f in features] != expected:
        raise DocError("breakdown IDs must run " + ", ".join(expected) + " with no gaps")
    slugs = [f.slug for f in features]
    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    if duplicates:
        raise DocError("breakdown has duplicate slugs: " + ", ".join(duplicates))
    return features


def parse_standards(text: str) -> Standards:
    lines = _lines(text)
    command = _first_match(_TEST_COMMAND, lines)
    if not command:
        raise DocError("STANDARDS.md needs a line like: Test command: `python3 -m unittest`")
    files = _first_match(_TEST_FILES, lines)
    globs = re.findall(r"`([^`]+)`", files.group(1)) if files else []
    if not globs:
        raise DocError("STANDARDS.md needs a line like: Test files: `tests/**/*.py`")
    return Standards(command.group(1), tuple(globs))


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    parts = re.findall(r"\*\*/|\*\*|\*|\?|[^*?]+", pattern)
    return re.compile("".join(_GLOB_TOKENS.get(p) or re.escape(p) for p in parts))


def mentions_id(text: str, behaviour_id: str) -> bool:
    """Whether text names the Behaviour, as `01-B2`, `01_B2` or `01_b2`: test names are often snake_case."""
    feature, k = _BEHAVIOUR_ID.fullmatch(behaviour_id).groups()
    pattern = _BEFORE + feature + "[-_][Bb]" + k + _AFTER
    return re.search(pattern, text) is not None
