"""CLI contract, home, game discovery, tools lock resolution, sync."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from helpers import CL, ROOT, ForgeCase, make_game

from mrforge import __version__
from mrforge.util import ForgeError


class CliContract(ForgeCase):
    with_game = False

    def test_version_json(self):
        code, d = self.cli("version")
        self.assertEqual(code, 0)
        self.assertEqual(set(d), {"ok", "command", "version", "data", "errors", "warnings", "gaps"})
        self.assertEqual(d["data"]["version"], __version__)

    def test_usage_error_exit_2(self):
        code, d = self.cli("tex", "hue")
        self.assertEqual(code, 2)
        self.assertEqual(d["errors"][0]["code"], "USAGE")

    def test_environment_error_exit_3(self):
        os.environ["MRFORGE_GAME"] = str(self.tmp / "nope")
        code, d = self.cli("game")
        self.assertEqual(code, 3)
        self.assertEqual(d["errors"][0]["code"], "GAME_NOT_FOUND")

    def test_global_options_anywhere(self):
        code, d = self.cli("--pretty", "version")
        self.assertEqual(code, 0)
        code, d = self.cli("game", "--game", str(self.tmp / "nope"))
        self.assertEqual(d["errors"][0]["code"], "GAME_NOT_FOUND")

    def test_capabilities_generated_from_parser(self):
        from mrforge.cli import _walk, parser
        code, d = self.cli("capabilities", "--offline")
        names = {c["command"] for c in d["data"]["commands"]}
        leaves = {c["command"] for c in _walk(parser(), "")}
        self.assertEqual(names, leaves)
        for must in ("build", "validate", "tex hue", "mat set", "deploy", "plan", "skin"):
            self.assertIn(must, names)
        src = (ROOT / "src" / "mrforge" / "cli.py").read_text(encoding="utf-8")
        self.assertNotIn('"tex hue", "tex tint"', src)  # no hand-kept command list

    def test_runs_from_awkward_path(self):
        odd = self.tmp / "dir with space ! (x)"
        odd.mkdir()
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        p = subprocess.run([sys.executable, "-m", "mrforge", "version"], cwd=odd, capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["data"]["version"], __version__)

    def test_cmd_launcher_from_awkward_path(self):
        if os.name != "nt":
            self.skipTest("Windows launcher")
        odd = self.tmp / "forge copy ! (x)"
        shutil.copytree(ROOT / "src", odd / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(ROOT / "mrforge.cmd", odd / "mrforge.cmd")
        p = subprocess.run([str(odd / "mrforge.cmd"), "version"], cwd=odd, capture_output=True,
                           env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["data"]["version"], __version__)
        p = subprocess.run([str(odd / "mrforge.cmd"), "knowledge", "no-such-topic"], cwd=odd, capture_output=True,
                           env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_cmd_launcher_keeps_exit_code_with_venv(self):
        # The .venv branch once ran inside a parenthesised block, where %ERRORLEVEL% is expanded before the
        # program runs, so every failure exited 0.
        if os.name != "nt":
            self.skipTest("Windows launcher")
        odd = self.tmp / "forge venv ! (x)"
        odd.mkdir()
        shutil.copyfile(ROOT / "mrforge.cmd", odd / "mrforge.cmd")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(odd / ".venv")], check=True,
                       capture_output=True)
        (odd / ".venv" / "Lib" / "site-packages" / "mrforge-src.pth").write_text(str(ROOT / "src") + "\n",
                                                                               encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        p = subprocess.run([str(odd / "mrforge.cmd"), "version"], cwd=odd, capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = subprocess.run([str(odd / "mrforge.cmd"), "knowledge", "no-such-topic"], cwd=odd, capture_output=True,
                           env=env)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        p = subprocess.run([str(odd / "mrforge.cmd"), "no-such-command"], cwd=odd, capture_output=True, env=env)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)


class Home(ForgeCase):
    with_game = False

    def test_home_layout_and_config(self):
        from mrforge.home import config, home, save_config
        h = home()
        for s in ("tools", "cache/usmap", "cache/index", "logs", "receipts"):
            self.assertTrue((h / s).is_dir(), s)
        self.assertEqual(config()["deploy_prefix"], "ZZZ")
        save_config({"deploy_prefix": "ZZY"})
        self.assertEqual(config()["deploy_prefix"], "ZZY")

    def test_log_written(self):
        self.cli("version")
        from mrforge.home import home
        self.assertIn('"cli"', (home() / "logs" / "mrforge.log").read_text(encoding="utf-8"))


class Game(ForgeCase):
    with_game = False

    def _steam(self):
        steam = self.tmp / "steam"
        lib = self.tmp / "lib two"
        (steam / "steamapps").mkdir(parents=True)
        (lib / "steamapps" / "common").mkdir(parents=True)
        (steam / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n "0"\n {\n  "path"  "%s"\n }\n "1"\n {\n  "path"  "%s"\n }\n}\n'
            % (str(steam).replace("\\", "\\\\"), str(lib).replace("\\", "\\\\")), encoding="utf-8")
        (lib / "steamapps" / "appmanifest_2767030.acf").write_text('"AppState"\n{\n "installdir" "MarvelRivals"\n}\n',
                                                                   encoding="utf-8")
        make_game(lib / "steamapps" / "common" / "MarvelRivals")
        return steam, lib

    def test_steam_discovery(self):
        from mrforge.game import find_in_steam
        steam, lib = self._steam()
        self.assertEqual(find_in_steam([steam]), lib / "steamapps" / "common" / "MarvelRivals")

    def test_order_and_layout(self):
        from mrforge import game as G
        g = make_game(self.tmp / "g")
        os.environ["MRFORGE_GAME"] = str(g)
        root, src = G.find_game()
        self.assertEqual(src, "MRFORGE_GAME")
        root, src = G.find_game(str(g))
        self.assertEqual(src, "--game")
        self.assertEqual(G.version(g), {"version": f"1.1.{CL}", "changelist": CL})
        ld = G.loader(g)
        self.assertTrue(ld["present"])
        (g / "x_loadOrder.json").write_text("{}", encoding="utf-8")
        self.assertTrue(G.mod_manager(g)["vortex"])

    def test_missing_loader_reported(self):
        from mrforge import game as G
        g = make_game(self.tmp / "g", loader=False)
        self.assertFalse(G.loader(g)["present"])


def _zip(path: Path, files: dict, top: str | None = None):
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in files.items():
            zf.writestr(f"{top}/{n}" if top else n, data)


class Tools(ForgeCase):
    with_game = False

    def _lock(self, asset: Path, exe_bytes: bytes, url: str | None = None):
        return {"tools": [{"name": "demo", "repo": "x/y", "tag": "v1", "asset": asset.name,
                           "asset_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "exe": "demo.exe",
                           "exe_sha256": hashlib.sha256(exe_bytes).hexdigest(), "probe": None, "probe_expect": None,
                           "url": url or asset.as_uri()}]}

    def setUp(self):
        super().setUp()
        os.environ.pop("MRFORGE_SHIM_DEMO", None)

    def test_download_good_hash_and_flatten(self):
        from mrforge.tools import exe_path, setup
        a = self.tmp / "demo.zip"
        _zip(a, {"demo.exe": b"EXE", "readme.txt": b"r"}, top="demo-win64")
        lk = self._lock(a, b"EXE")
        r = setup(lk=lk)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["tools"][0]["source"], "download")
        self.assertEqual(exe_path(lk["tools"][0]).read_bytes(), b"EXE")
        r2 = setup(lk=lk)
        self.assertEqual(r2["tools"][0]["source"], "installed")

    def test_bad_asset_hash(self):
        from mrforge.tools import setup
        a = self.tmp / "demo.zip"
        _zip(a, {"demo.exe": b"EXE"})
        lk = self._lock(a, b"EXE")
        lk["tools"][0]["asset_sha256"] = "0" * 64
        r = setup(lk=lk)
        self.assertEqual(r["errors"][0]["code"], "TOOL_ASSET_HASH_MISMATCH")

    def test_bad_exe_hash(self):
        from mrforge.tools import setup
        a = self.tmp / "demo.zip"
        _zip(a, {"demo.exe": b"EXE"})
        lk = self._lock(a, b"OTHER")
        self.assertEqual(setup(lk=lk)["errors"][0]["code"], "TOOL_EXE_HASH_MISMATCH")

    def test_offline_missing(self):
        from mrforge.tools import setup
        a = self.tmp / "demo.zip"
        _zip(a, {"demo.exe": b"EXE"})
        r = setup(lk=self._lock(a, b"EXE"), offline=True)
        self.assertEqual(r["errors"][0]["code"], "TOOL_UNAVAILABLE_OFFLINE")

    def test_adopt_from_folder(self):
        from mrforge.tools import setup
        a = self.tmp / "demo.zip"
        _zip(a, {"demo.exe": b"EXE"})
        coll = self.tmp / "collection" / "demo-copy"
        coll.mkdir(parents=True)
        (coll / "demo.exe").write_bytes(b"EXE")
        (coll / "extra.dll").write_bytes(b"D")
        lk = self._lock(a, b"EXE", url="file:///nonexistent")
        r = setup(lk=lk, from_dirs=[str(self.tmp / "collection")], offline=True)
        self.assertEqual(r["tools"][0]["source"], "from")

    def test_adopt_plugin_folder_only(self):
        """A lock exe under a plugin folder (Plugin/Binaries/...) adopts that folder, never its siblings (found
        2026-11-25: --from copied a whole 1.6 GB tool collection)."""
        from mrforge.tools import setup, tool_dir
        a = self.tmp / "demo.zip"
        _zip(a, {"Plug/Binaries/demo.dll": b"DLL"})
        coll = self.tmp / "collection"
        (coll / "Plug" / "Binaries").mkdir(parents=True)
        (coll / "Plug" / "Binaries" / "demo.dll").write_bytes(b"DLL")
        (coll / "Plug" / "Plug.uplugin").write_text("{}")
        (coll / "UnrelatedTool").mkdir()
        (coll / "UnrelatedTool" / "big.bin").write_bytes(b"X")
        lk = self._lock(a, b"DLL", url="file:///nonexistent")
        lk["tools"][0]["exe"] = "Plug/Binaries/demo.dll"
        r = setup(lk=lk, from_dirs=[str(coll)], offline=True)
        self.assertEqual(r["tools"][0]["source"], "from", r)
        d = tool_dir(lk["tools"][0])
        self.assertTrue((d / "Plug" / "Plug.uplugin").is_file())
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["Plug"])

    def test_unsafe_archive(self):
        from mrforge.tools import setup
        a = self.tmp / "demo.zip"
        _zip(a, {"../evil.exe": b"EXE", "demo.exe": b"EXE"})
        self.assertEqual(setup(lk=self._lock(a, b"EXE"))["errors"][0]["code"], "UNSAFE_ARCHIVE")

    def test_real_lock_is_complete(self):
        from mrforge.tools import lock
        for t in lock()["tools"]:
            for k in ("name", "repo", "tag", "asset", "asset_sha256", "exe", "exe_sha256", "license"):
                self.assertTrue(t.get(k), f"{t['name']} {k}")
            self.assertEqual(len(t["asset_sha256"]), 64)


class Sync(ForgeCase):
    with_game = False

    def _fetch(self, builds, key="0xSECRETKEY0123456789"):
        listing = json.dumps([{"name": f"5.3.2-{b}+++depot_marvel+S11.0_release-Marvel.usmap",
                               "download_url": f"https://x/{b}", "size": 2000} for b in builds]).encode()

        def fetch(url):
            if url.endswith("/usmap"):
                return listing
            if url.endswith("AES.json"):
                return json.dumps({"mainKey": key}).encode()
            return b"U" * 2048
        return fetch

    def test_exact_match(self):
        from mrforge.sync import sync, usmap_for
        r = sync(CL, fetch=self._fetch([CL - 5, CL, CL + 9]))
        self.assertTrue(r["exact"])
        self.assertEqual(r["build"], CL)
        self.assertIsNotNone(usmap_for(CL))

    def test_mismatch_names_nearest(self):
        from mrforge.sync import sync
        with self.assertRaises(ForgeError) as cm:
            sync(CL, fetch=self._fetch([CL - 5, CL - 50]))
        self.assertEqual(cm.exception.code, "USMAP_BUILD_MISMATCH")
        self.assertIn(str(CL - 5), cm.exception.message)
        r = sync(CL, fetch=self._fetch([CL - 5]), allow_nearest=True)
        self.assertFalse(r["exact"])

    def test_offline_uses_cache(self):
        from mrforge.sync import sync
        sync(CL, fetch=self._fetch([CL]))
        r = sync(CL, offline=True)
        self.assertEqual(r["source"], "cache")
        with self.assertRaises(ForgeError):
            sync(CL + 1, offline=True)

    def test_key_never_printed(self):
        import mrforge.sync as S
        secret = "0xTOPSECRET99999"
        orig = S.default_fetch
        S.default_fetch = self._fetch([CL], key=secret)
        try:
            g = make_game(self.tmp / "g")
            code, d = self.cli("sync", "--game", str(g))
            self.assertEqual(code, 0)
            self.assertNotIn(secret, json.dumps(d))
            from mrforge.home import home
            self.assertNotIn(secret, (home() / "logs" / "mrforge.log").read_text(encoding="utf-8"))
            self.assertEqual(S.aes_key(), secret)
        finally:
            S.default_fetch = orig
