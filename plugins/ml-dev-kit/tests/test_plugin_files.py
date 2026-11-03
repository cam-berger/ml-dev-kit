"""Checks on the plugin's prompt files: frontmatter and the reply formats the orchestrator parses."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import PLUGIN, REPO
from mdk.cli import _COMMANDS
from mdk.docs import SPEC_SECTIONS, parse_standards, spec_problems

AGENTS = ("implementer", "reviewer", "spec-checker")
SKILL = PLUGIN / "skills/feature"
REFERENCES = ("references/setup.md", "references/spec.md", "references/build.md")


def frontmatter(path: Path) -> dict[str, str]:
    """The `key: value` lines between the first two `---` lines, with surrounding quotes stripped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} does not start with ---")
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError(f"{path} has no closing ---")
    fields = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


class AgentFileTests(unittest.TestCase):
    def test_agents_have_required_frontmatter(self):
        for name in AGENTS:
            fm = frontmatter(PLUGIN / f"agents/{name}.md")
            self.assertEqual(fm["name"], name)
            self.assertTrue(fm["description"])
            self.assertEqual(fm["model"], "inherit")

    def test_implementer_cannot_spawn_agents(self):
        self.assertIn("Agent", frontmatter(PLUGIN / "agents/implementer.md")["disallowedTools"])

    def test_read_only_agents_cannot_write(self):
        for name in ("reviewer", "spec-checker"):
            tools = frontmatter(PLUGIN / f"agents/{name}.md")["tools"]
            self.assertNotIn("Write", tools)
            self.assertNotIn("Edit", tools)

    def test_reviewer_reply_format(self):
        body = (PLUGIN / "agents/reviewer.md").read_text(encoding="utf-8")
        for s in ("## Spec and Deviations", "## Standards", "Verdict:"):
            self.assertIn(s, body)

    def test_implementer_reply_format(self):
        body = (PLUGIN / "agents/implementer.md").read_text(encoding="utf-8")
        for s in ("Status:", "Deviations:", "Evidence:", "Noticed:"):
            self.assertIn(s, body)

    def test_fix_round_reports_are_cumulative(self):
        # The Reviewer judges one self-contained report; a delta report would look like missing RED evidence.
        implementer = (PLUGIN / "agents/implementer.md").read_text(encoding="utf-8")
        fix_rounds = implementer.split("## Fix rounds")[1].split("\n## ")[0]
        for s in ("cumulative report", "`Deviations:`, `Evidence:` and `Noticed:`"):
            self.assertIn(s, fix_rounds)
        self.assertNotIn("newly saw", fix_rounds)  # the orchestrator records Noticed once, from the last report
        reviewer = (PLUGIN / "agents/reviewer.md").read_text(encoding="utf-8")
        self.assertIn("latest, cumulative report", reviewer)

    def test_spec_checker_reply_format(self):
        body = (PLUGIN / "agents/spec-checker.md").read_text(encoding="utf-8")
        self.assertIn("nothing important left", body)


def _skill_texts() -> dict[str, str]:
    return {rel: (SKILL / rel).read_text(encoding="utf-8") for rel in ("SKILL.md", *REFERENCES)}


class SkillFileTests(unittest.TestCase):
    def test_feature_skill_is_user_only(self):
        fm = frontmatter(SKILL / "SKILL.md")
        self.assertEqual(fm["name"], "feature")
        self.assertEqual(fm["disable-model-invocation"], "true")
        self.assertIn("argument-hint", fm)
        # Unquoted, [goal] parses as a YAML list rather than a hint string.
        self.assertIn('argument-hint: "[goal]"', (SKILL / "SKILL.md").read_text(encoding="utf-8"))

    def test_skill_references_exist(self):
        for r in REFERENCES:
            self.assertTrue((SKILL / r).is_file(), r)

    def test_spec_template_sections_in_order(self):
        t = (SKILL / "templates/spec.md").read_text(encoding="utf-8")
        idx = [t.index(f"## {s}") for s in SPEC_SECTIONS]
        self.assertEqual(idx, sorted(idx))

    def test_spec_from_template_passes_mdk_checks(self):
        # A Spec copied from the template must get past `mdk await spec` once NN is filled in.
        t = (SKILL / "templates/spec.md").read_text(encoding="utf-8")
        self.assertEqual(spec_problems(t.replace("NN", "01"), "01"), [])

    def test_standards_template_parses(self):
        parse_standards((SKILL / "templates/standards.md").read_text(encoding="utf-8"))

    def test_standards_template_gives_each_glob_its_own_backticks(self):
        # parse_standards reads `a, b` as one glob that matches nothing.
        t = (SKILL / "templates/standards.md").read_text(encoding="utf-8")
        self.assertIn("its own backticks", t)
        self.assertIn("`tests/**/*.py`, `src/**/*_test.py`", t)

    def test_setup_checks_machine_lines_before_they_lock(self):
        # After setup STANDARDS.md is the human's, so a broken line would only show in Build, unfixable.
        setup = (SKILL / "references/setup.md").read_text(encoding="utf-8")
        locked = setup.index("`mdk await standards`")
        for phrase in ("Run the drafted test command and time it", "8 minutes", "git ls-files"):
            self.assertLess(setup.index(phrase), locked, phrase)

    def test_build_reference_caps_fix_loop_at_3(self):
        build = (SKILL / "references/build.md").read_text(encoding="utf-8")
        self.assertRegex(build, r"Fix rounds are capped at 3\. If the third round [^\n]*`mdk escalate NN ")

    def test_skill_names_only_real_mdk_commands(self):
        for rel, text in _skill_texts().items():
            for command in re.findall(r"`mdk (\w+)", text):
                self.assertIn(command, _COMMANDS, f"{rel} names mdk {command}")

    def test_skill_dispatches_only_shipped_agents(self):
        for rel, text in _skill_texts().items():
            for name in re.findall(r"ml-dev-kit:([a-z-]+)", text):
                self.assertTrue(name == "feature" or name in AGENTS, f"{rel} dispatches {name}")

    def test_skill_files_stay_short(self):
        # Long prompts go unread; the limits come from the design's anti-goals.
        limits = {SKILL / "SKILL.md": 80, REPO / "README.md": 60, **{SKILL / r: 100 for r in REFERENCES}}
        for path, limit in limits.items():
            self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), limit, path.name)

    def test_notice_attributes_sources(self):
        n = (REPO / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("Matt Pocock", n)
        self.assertIn("Jesse Vincent", n)


if __name__ == "__main__":
    unittest.main()
