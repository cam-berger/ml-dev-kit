from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN, REPO, make_repo


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_marketplace_lists_plugin(self):
        m = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(m["name"], "ml-dev-kit")
        self.assertEqual(m["plugins"][0]["source"], "./plugins/ml-dev-kit")

    def test_plugin_manifest(self):
        p = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(p["name"], "ml-dev-kit")
        self.assertIn("version", p)

    def test_make_repo_commits(self):  # helper sanity
        root = make_repo(Path(self.tmp), {"a.txt": "x"})
        out = subprocess.run(
            ["git", "log", "--oneline"], cwd=root, capture_output=True, text=True
        ).stdout
        self.assertIn("init", out)


if __name__ == "__main__":
    unittest.main()
