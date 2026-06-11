# -*- coding: utf-8 -*-
"""
End-to-end smoke tests for build_from_html.py and build_vault.py.

These run each script as a real subprocess inside a throw-away vault laid out the
way the scripts expect (script in <vault>/_tools/, output written one level up),
then assert on the generated notes. Running the real CLI keeps the tests honest
across internal refactors. Standard library only — run with:

    python -m unittest discover -s tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "fixtures")


class _ScriptRun:
    """A script executed inside a temp vault; exposes the generated paths."""

    def __init__(self, vault, script):
        self.vault = vault
        self.posts_dir = os.path.join(vault, "Posts")
        self.attachments = os.path.join(vault, "attachments")
        self.index = os.path.join(vault, "_Analytics", "Post index.md")
        self.script = script

    def note(self, name):
        with open(os.path.join(self.posts_dir, name), encoding="utf-8") as f:
            return f.read()

    def post_names(self):
        return sorted(os.listdir(self.posts_dir))


class BuildScriptTests(unittest.TestCase):
    def _run(self, script, fixture, channel="testchan"):
        """Lay out <tmp>/_tools/<script>, run it against the fixture export."""
        tmp = tempfile.mkdtemp(prefix="tg2obs_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        tools = os.path.join(tmp, "_tools")
        os.makedirs(tools)
        script_path = os.path.join(tools, script)
        shutil.copy(os.path.join(REPO, script), script_path)

        export = os.path.join(FIXTURES, fixture)
        result = subprocess.run(
            [sys.executable, script_path, export, "--channel", channel],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"script failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        return _ScriptRun(tmp, script_path)

    # ── shared expectations both formats must satisfy ──────────────────────────
    def _assert_common(self, run):
        # service message skipped, two real posts written with the id-padded names
        self.assertEqual(run.post_names(),
                         ["2022-05-26 id00002.md", "2022-05-26 id00003.md"])

        post2 = run.note("2022-05-26 id00002.md")
        self.assertIn("tg_id: 2", post2)
        self.assertIn("channel: testchan", post2)
        self.assertIn("url: https://t.me/testchan/2", post2)
        self.assertIn("Hello **world**", post2)          # bold mapped to markdown
        self.assertIn("![[attachments/", post2)          # photo embedded
        self.assertIn("## 🔍 Analysis", post2)

        # the post index lists both posts and the total
        with open(run.index, encoding="utf-8") as f:
            index = f.read()
        self.assertIn("Total: **2**", index)
        self.assertIn("[[2022-05-26 id00002]]", index)

    def test_html_export(self):
        run = self._run("build_from_html.py", "html_export")
        self._assert_common(run)
        # the HTML script resolves a reply into a wikilink via the id map
        post3 = run.note("2022-05-26 id00003.md")
        self.assertIn("[[2022-05-26 id00002|#2]]", post3)
        # HTML keeps the original media basename
        self.assertIn("![[attachments/photo_2.jpg]]", run.note("2022-05-26 id00002.md"))
        self.assertTrue(os.path.isfile(os.path.join(run.attachments, "photo_2.jpg")))

    def test_json_export(self):
        run = self._run("build_vault.py", "json_export")
        self._assert_common(run)
        # the JSON script renders the reply as a plain #id reference
        post3 = run.note("2022-05-26 id00003.md")
        self.assertIn("Reply to #2", post3)
        # JSON prefixes the media basename with the message id to avoid collisions
        self.assertIn("![[attachments/2_photo_2.jpg]]", run.note("2022-05-26 id00002.md"))
        self.assertTrue(os.path.isfile(os.path.join(run.attachments, "2_photo_2.jpg")))

    # ── the core re-run contract: text is rebuilt, Analysis is preserved ───────
    def test_analysis_section_preserved_on_rerun_html(self):
        self._assert_rerun_keeps_analysis("build_from_html.py", "html_export")

    def test_analysis_section_preserved_on_rerun_json(self):
        self._assert_rerun_keeps_analysis("build_vault.py", "json_export")

    def _assert_rerun_keeps_analysis(self, script, fixture):
        run = self._run(script, fixture)
        note_path = os.path.join(run.posts_dir, "2022-05-26 id00002.md")

        # user writes a note under the Analysis marker
        original = run.note("2022-05-26 id00002.md")
        edited = original.replace("_not analyzed yet_", "MY CUSTOM ANALYSIS")
        self.assertNotEqual(original, edited)
        with open(note_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(edited)

        # re-run the same script in place (same vault)
        export = os.path.join(FIXTURES, fixture)
        result = subprocess.run(
            [sys.executable, run.script, export, "--channel", "testchan"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        after = run.note("2022-05-26 id00002.md")
        self.assertIn("MY CUSTOM ANALYSIS", after)        # user content kept
        self.assertNotIn("_not analyzed yet_", after)     # not duplicated/reset
        self.assertEqual(after.count("## 🔍 Analysis"), 1)  # exactly one section


if __name__ == "__main__":
    unittest.main()
