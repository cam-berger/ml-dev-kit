from __future__ import annotations

import unittest

from helpers import BREAKDOWN_OK, STANDARDS_OK, spec_text
from mdk.docs import (
    DocError,
    PlannedFeature,
    Standards,
    behaviour_ids,
    glob_to_regex,
    mentions_id,
    parse_breakdown,
    parse_standards,
    spec_body_hash,
    spec_problems,
    text_hash,
)


class BehaviourIdTests(unittest.TestCase):
    def test_behaviour_ids_in_order(self):
        self.assertEqual(behaviour_ids(spec_text()), ["01-B1", "01-B2"])

    def test_behaviour_ids_ignore_other_sections(self):
        t = spec_text().replace("## Intent\n", "## Intent\nSee 01-B9.\n")
        self.assertEqual(behaviour_ids(t), ["01-B1", "01-B2"])

    def test_behaviour_ids_are_unique(self):
        t = spec_text().replace("## Interface", "- 01-B1 again\n\n## Interface")
        self.assertEqual(behaviour_ids(t), ["01-B1", "01-B2"])


class SpecProblemTests(unittest.TestCase):
    def test_spec_problems_ok(self):
        self.assertEqual(spec_problems(spec_text(), "01"), [])

    def test_spec_problems_missing_section(self):
        t = spec_text().replace("## Out of scope", "## Later")
        self.assertTrue(any("Out of scope" in p for p in spec_problems(t, "01")))

    def test_spec_problems_deviations_not_last(self):
        moved = spec_text().replace("## Deviations\n", "").replace(
            "## Out of scope\n", "## Deviations\n## Out of scope\n"
        )
        self.assertTrue(any("Deviations" in p for p in spec_problems(moved, "01")))

    def test_spec_problems_sections_out_of_order(self):
        swapped = (
            spec_text()
            .replace("## Intent", "## X")
            .replace("## Behaviours", "## Intent")
            .replace("## X", "## Behaviours")
        )
        self.assertTrue(any("order" in p for p in spec_problems(swapped, "01")))

    def test_spec_problems_wrong_prefix(self):
        self.assertTrue(any("02-B1" in p for p in spec_problems(spec_text("02"), "01")))

    def test_spec_problems_no_behaviours(self):
        self.assertTrue(spec_problems(spec_text(behaviours=()), "01"))

    def test_spec_problems_only_h2_lines_are_sections(self):
        t = spec_text().replace("## Intent\n", "## Intent\n### Detail\nText.\n")
        self.assertEqual(spec_problems(t, "01"), [])

    def test_spec_problems_accept_crlf(self):
        self.assertEqual(spec_problems(spec_text().replace("\n", "\r\n"), "01"), [])

    def test_spec_problems_flag_behaviour_lines_without_an_id(self):
        # I5: a line like `- **B3** —` would otherwise be a Behaviour that no test is ever asked for.
        for line in ("- **B3** — Admins see a report.", "* Admins see a report.", "3. Admins see a report."):
            with self.subTest(line=line):
                t = spec_text().replace("\n## Interface", f"{line}\n\n## Interface")
                self.assertEqual(spec_problems(t, "01"), [f"this Behaviours line has no ID such as 01-B1: {line}"])

    def test_spec_problems_allow_detail_lines_and_references(self):
        t = spec_text().replace(
            "\n## Interface",
            "  - for example, an empty name\n- **01-B3** — like 01-B1, for admins.\nPlain text under the list.\n\n## Interface",
        )
        self.assertEqual(spec_problems(t, "01"), [])

    def test_spec_problems_flag_duplicate_ids(self):
        t = spec_text().replace("\n## Interface", "- **01-B1** — Something else.\n\n## Interface")
        self.assertEqual(spec_problems(t, "01"), ["behaviour ID 01-B1 is used by more than one line"])

    def test_sections_and_the_deviations_cut_read_headings_the_same_way(self):
        # I5: a heading the section check accepts must also end the hashed body, or Deviations void the Approval.
        t = spec_text().replace("## Deviations", "##  Deviations")
        self.assertEqual(spec_problems(t, "01"), [])
        self.assertEqual(spec_body_hash(t), spec_body_hash(t + "- Used a queue.\n"))


class HashTests(unittest.TestCase):
    def test_body_hash_ignores_deviations(self):
        added = spec_text() + "\n- 01-B1: returns 423 for locked accounts\n"
        self.assertEqual(spec_body_hash(spec_text()), spec_body_hash(added))

    def test_body_hash_sees_body_changes(self):
        changed = spec_text().replace("## Intent\n", "## Intent\nNew.\n")
        self.assertNotEqual(spec_body_hash(spec_text()), spec_body_hash(changed))

    def test_body_hash_ignores_line_endings(self):
        crlf = spec_text().replace("\n", "\r\n")
        self.assertEqual(spec_body_hash(spec_text()), spec_body_hash(crlf))

    def test_body_hash_ignores_trailing_whitespace(self):
        padded = spec_text().replace("## Intent\n", "## Intent   \n") + "\n\n"
        self.assertEqual(spec_body_hash(spec_text()), spec_body_hash(padded))

    def test_text_hash_covers_deviations(self):
        added = spec_text() + "\n- 01-B1: returns 423 for locked accounts\n"
        self.assertNotEqual(text_hash(spec_text()), text_hash(added))

    def test_text_hash_ignores_line_endings_and_trailing_whitespace(self):
        noisy = spec_text().replace("\n", "  \r\n") + "\n"
        self.assertEqual(text_hash(spec_text()), text_hash(noisy))

    def test_hashes_are_sha256_hex(self):
        self.assertRegex(spec_body_hash(spec_text()), r"^[0-9a-f]{64}$")
        self.assertRegex(text_hash(spec_text()), r"^[0-9a-f]{64}$")


class BreakdownTests(unittest.TestCase):
    def test_parse_breakdown(self):
        self.assertEqual(
            parse_breakdown(BREAKDOWN_OK)[1],
            PlannedFeature("02", "login", "Users sign in."),
        )

    def test_parse_breakdown_accepts_hyphen(self):
        self.assertEqual(len(parse_breakdown(BREAKDOWN_OK.replace(" — ", " - "))), 2)

    def test_parse_breakdown_ignores_other_lines(self):
        t = "# Breakdown\n\nIntro text.\n" + BREAKDOWN_OK + "\nTrailing note.\n"
        self.assertEqual([f.id for f in parse_breakdown(t)], ["01", "02"])

    def test_parse_breakdown_rejects_gap(self):
        with self.assertRaises(DocError):
            parse_breakdown("01. a — x\n03. b — y\n")

    def test_parse_breakdown_rejects_duplicate_slug(self):
        with self.assertRaisesRegex(DocError, "duplicate"):
            parse_breakdown("01. a — x\n02. a — y\n")

    def test_parse_breakdown_rejects_empty(self):
        with self.assertRaises(DocError):
            parse_breakdown("# Breakdown\n")


class StandardsTests(unittest.TestCase):
    def test_parse_standards(self):
        self.assertEqual(
            parse_standards(STANDARDS_OK),
            Standards("python3 -m unittest discover -s tests -v", ("tests/**/*.py",)),
        )

    def test_parse_standards_several_globs(self):
        t = "Test command: `make test`\nTest files: `a/*.py`, `b/**/*.ts`\n"
        self.assertEqual(parse_standards(t).test_globs, ("a/*.py", "b/**/*.ts"))

    def test_parse_standards_missing_command(self):
        with self.assertRaisesRegex(DocError, "Test command"):
            parse_standards("Test files: `t/*.py`\n")

    def test_parse_standards_missing_files(self):
        with self.assertRaisesRegex(DocError, "Test files"):
            parse_standards("Test command: `make test`\n")


class MatchingTests(unittest.TestCase):
    def test_glob_to_regex(self):
        r = glob_to_regex("tests/**/*.py")
        self.assertTrue(r.fullmatch("tests/a.py"))
        self.assertTrue(r.fullmatch("tests/x/y/a.py"))
        self.assertFalse(r.fullmatch("src/a.py"))
        self.assertTrue(glob_to_regex("**/*.test.ts").fullmatch("a.test.ts"))
        self.assertFalse(glob_to_regex("*.py").fullmatch("d/a.py"))

    def test_glob_to_regex_escapes_and_single_char(self):
        r = glob_to_regex("t?.py")
        self.assertTrue(r.fullmatch("ta.py"))
        self.assertFalse(r.fullmatch("ta/py"))
        self.assertFalse(r.fullmatch("tapy"))
        self.assertFalse(glob_to_regex("a+b").fullmatch("aab"))

    def test_mentions_id(self):
        self.assertTrue(mentions_id("def test_01_B2_x():", "01-B2"))
        self.assertTrue(mentions_id("# 01-B2", "01-B2"))
        self.assertFalse(mentions_id("01-B21", "01-B2"))
        self.assertFalse(mentions_id("101-B2", "01-B2"))

    def test_mentions_id_accepts_a_lowercase_b(self):
        # M5: linters want snake_case test names, and pytest prints them as written.
        self.assertTrue(mentions_id("def test_01_b2_rejects_empty_name():", "01-B2"))
        self.assertTrue(mentions_id("tests/test_a.py::test_01_b2 PASSED", "01-B2"))
        self.assertFalse(mentions_id("test_01_b21", "01-B2"))
        self.assertFalse(mentions_id("test_01_c2", "01-B2"))


if __name__ == "__main__":
    unittest.main()
