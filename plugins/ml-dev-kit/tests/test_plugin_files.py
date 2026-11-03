"""Checks on the plugin's prompt files: frontmatter and the reply formats the orchestrator parses."""
from __future__ import annotations

import unittest
from pathlib import Path

from helpers import PLUGIN

AGENTS = ("implementer", "reviewer", "spec-checker")


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
        for s in ("cumulative report", "Deviations", "Evidence"):
            self.assertIn(s, fix_rounds)
        reviewer = (PLUGIN / "agents/reviewer.md").read_text(encoding="utf-8")
        self.assertIn("latest, cumulative report", reviewer)

    def test_spec_checker_reply_format(self):
        body = (PLUGIN / "agents/spec-checker.md").read_text(encoding="utf-8")
        self.assertIn("nothing important left", body)


if __name__ == "__main__":
    unittest.main()
