"""Release hygiene: version mirrors agree; tracked public files carry no machine paths or personal names."""
import re
import subprocess
import unittest

from helpers import ROOT

from mrforge import __version__


class Docs(unittest.TestCase):
    def test_version_mirrors(self):
        top = re.search(r"^## (\d+\.\d+\.\d+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
        self.assertEqual(top, __version__)
        skill = (ROOT / "skills" / "marvelrivals-forge" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"version: {__version__}", skill)
        state = (ROOT / "STATE.md").read_text(encoding="utf-8")
        self.assertIn(__version__, state)

    def test_no_machine_paths_in_tracked_files(self):
        try:
            files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        drive = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?!/)")
        personal = re.compile(r"karlo|\\Users\\[A-Za-z]|/Users/[A-Za-z]|SteamLibrary|Vortex Mods", re.I)
        bad = []
        for f in files:
            p = ROOT / f
            if p.suffix.lower() in (".png", ".zip", ".usmap") or not p.is_file() or f.startswith("tests/"):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for n, line in enumerate(text.splitlines(), 1):
                if drive.search(line) or personal.search(line):
                    bad.append(f"{f}:{n}: {line.strip()[:100]}")
        self.assertEqual(bad, [])
