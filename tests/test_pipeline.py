"""Whole loop through the CLI with tool shims: new -> extract -> edit -> build -> validate -> package -> deploy."""
import json
import os
import zipfile
from pathlib import Path

from helpers import CL, SKIN, ForgeCase, fake_mod


class Pipeline(ForgeCase):
    def setUp(self):
        super().setUp()
        self.ready()
        code, d = self.cli("new", "Red Cat", "--skin", SKIN, "--kind", "texture,material", "--out", str(self.tmp / "proj (1)"),
                           "--description", "test mod")
        self.assertEqual(code, 0, d)
        self.root = Path(d["data"]["project"])

    def run_cli(self, *a):
        return self.cli(*a, cwd=self.root)

    def test_texture_and_material_loop(self):
        code, d = self.run_cli("extract", "--textures", "T_*_Body_01_*", "--materials")
        self.assertEqual(code, 0, d)
        self.assertEqual((d["data"]["textures"], d["data"]["materials"]), (3, 2))
        code, d = self.run_cli("tex", "list")
        self.assertEqual(len(d["data"]["textures"]), 3)
        code, d = self.run_cli("build")
        self.assertEqual(d["errors"][0]["code"], "NOTHING_TO_BUILD")
        code, d = self.run_cli("tex", "hue", f"T_{SKIN}_Body_01_D", "--shift", "120")
        self.assertEqual(code, 0, d)
        code, d = self.run_cli("mat", "set", f"MI_{SKIN}_Body_01", "BaseTint", "#ff0000")
        self.assertEqual(code, 0, d)
        self.assertEqual(len(d["data"]["set"]), 2)  # game + Lobby copy
        code, d = self.run_cli("tex", "sheet")
        self.assertTrue(Path(d["data"]["sheet"]).is_file())
        code, d = self.run_cli("build")
        self.assertEqual(code, 0, d)
        self.assertEqual(d["data"]["packages"], 3)  # 1 texture + 2 materials, nothing else staged
        rc = json.loads((self.root / "dist" / "receipt.json").read_text(encoding="utf-8"))
        for k in ("changelist", "usmap_sha256", "tools", "staged_packages", "inputs", "outputs", "pack_argv"):
            self.assertTrue(rc.get(k), k)
        self.assertEqual(rc["options"], {"obfuscate": False, "strip": False, "encrypt": False})
        code, d = self.run_cli("validate")
        self.assertEqual(code, 0, d)
        st = {r["rule"]: r["status"] for r in d["data"]["rules"]}
        for rule in ("V-NAME", "V-FLAGS", "V-PATHS", "V-LEAK", "V-STALE", "V-RECEIPT", "V-TEX", "V-MAT", "V-CONFLICT"):
            self.assertEqual(st[rule], "pass", (rule, d["data"]["rules"]))
        self.assertEqual(d["data"]["tiers"]["load"], "not_run")
        code, d = self.run_cli("package")
        self.assertEqual(code, 0, d)
        z1 = Path(d["data"]["zip"]).read_bytes()
        code, d2 = self.run_cli("package")
        self.assertEqual(Path(d2["data"]["zip"]).read_bytes(), z1)
        names = zipfile.ZipFile(d["data"]["zip"]).namelist()
        self.assertEqual(names, ["RedCat/README.txt", "RedCat/RedCat_9999999_P.pak", "RedCat/RedCat_9999999_P.ucas",
                                 "RedCat/RedCat_9999999_P.utoc"])

    def _built(self):
        self.run_cli("extract", "--textures", "T_*_Body_01_D")
        self.run_cli("tex", "tint", f"T_{SKIN}_Body_01_D", "--color", "#00ff00")
        code, d = self.run_cli("build")
        self.assertEqual(code, 0, d)

    def _rules(self):
        code, d = self.run_cli("validate")
        return code, {r["rule"]: r for r in d["data"]["rules"]}

    def test_v_paths_misspelled_fails(self):
        self._built()
        utoc = self.root / "dist" / "RedCat_9999999_P.utoc"
        c = json.loads(utoc.read_text(encoding="utf-8"))
        bad = c["packages"][0].replace("T_", "T_Typo_")
        c["files"][bad] = c["files"].pop(c["packages"][0])
        c["packages"] = [bad]
        utoc.write_text(json.dumps(c), encoding="utf-8")
        code, r = self._rules()
        self.assertEqual(code, 1)
        self.assertEqual(r["V-PATHS"]["status"], "fail")
        self.assertEqual(r["V-RECEIPT"]["status"], "fail")

    def test_v_leak_and_flags(self):
        self._built()
        utoc = self.root / "dist" / "RedCat_9999999_P.utoc"
        c = json.loads(utoc.read_text(encoding="utf-8"))
        c["packages"].append(f"Marvel/Content/Marvel/Characters/1061/{SKIN}/Post_{SKIN}_Physics.uasset")
        c["flags"].append("Encrypted")
        utoc.write_text(json.dumps(c), encoding="utf-8")
        code, r = self._rules()
        self.assertEqual(r["V-LEAK"]["status"], "fail")
        self.assertEqual(r["V-FLAGS"]["status"], "fail")

    def test_v_name_and_stale(self):
        self._built()
        rc = self.root / "dist" / "receipt.json"
        d = json.loads(rc.read_text(encoding="utf-8"))
        d["changelist"] = CL - 1
        rc.write_text(json.dumps(d), encoding="utf-8")
        code, r = self._rules()
        self.assertEqual(r["V-STALE"]["status"], "fail")
        (self.root / "dist" / "RedCat_9999999_P.ucas").unlink()
        code, r = self._rules()
        self.assertEqual(r["V-NAME"]["status"], "fail")

    def test_conflict_warning(self):
        self._built()
        fake_mod(self.mods_dir, "AAA-other", "Other_9999999_P",
                 [f"Marvel/Content/Marvel/Characters/1061/{SKIN}/Textures/T_{SKIN}_Body_01_D.uasset"])
        code, r = self._rules()
        self.assertEqual(code, 0)
        self.assertEqual(r["V-CONFLICT"]["status"], "warn")

    def test_deploy_undeploy_exact(self):
        self._built()
        foreign = fake_mod(self.mods_dir, "AAA-keep", "Keep_9999999_P", ["Marvel/Content/a.uasset"])
        before = sorted(str(p) for p in self.mods_dir.rglob("*"))
        from mrforge import deploy as D
        with self.assertRaises(Exception) as cm:
            D.deploy(self.root, running=True)
        self.assertEqual(cm.exception.code, "GAME_RUNNING")
        r = D.deploy(self.root, running=False)
        self.assertTrue(Path(r["folder"]).name.startswith("ZZZ-mrforge-red-cat"))
        self.assertEqual(len(r["files"]), 3)
        self.assertTrue(D.status()["deployed"][0]["intact"])
        D.undeploy("red-cat", running=False)
        self.assertEqual(sorted(str(p) for p in self.mods_dir.rglob("*")), before)
        self.assertTrue((foreign / "Keep_9999999_P.utoc").is_file())

    def test_undeploy_keeps_changed_file(self):
        self._built()
        from mrforge import deploy as D
        r = D.deploy(self.root, running=False)
        Path(r["files"][0]).write_bytes(b"user changed this")
        u = D.undeploy("red-cat", running=False)
        self.assertEqual(len(u["kept"]), 1)
        self.assertFalse(u["folder_removed"])

    def test_extract_rejects_unknown_package(self):
        code, d = self.run_cli("extract", "--package", "Marvel/Content/Marvel/Characters/1061/9999999/Nope.uasset")
        self.assertEqual(d["errors"][0]["code"], "PACKAGE_NOT_IN_BUILD")


class CheckLoad(ForgeCase):
    def test_signatures_and_confirm(self):
        logs = self.tmp / "logs" / "Logs"
        logs.mkdir(parents=True)
        (logs / "2026.11.15-1.log").write_text("LogInit: ok\nLogPakFile: Error: Failed to mount ../~mods/X/RedCat_9999999_P.utoc\n"
                                               "LogX: RedCat_9999999_P mounted\nFatal error: boom\n", encoding="utf-8")
        self.ready()
        code, d = self.cli("new", "Red Cat", "--skin", SKIN, "--out", str(self.tmp / "p"))
        root = d["data"]["project"]
        code, d = self.cli("check-load", "--project", root)
        self.assertEqual(code, 0, d)
        sigs = {s["signature"] for s in d["data"]["logs"][0]["signatures"]}
        self.assertEqual(sigs, {"PAK_MOUNT_FAILED", "FATAL"})
        self.assertEqual(len(d["data"]["logs"][0]["mentions_of_mod"]), 2)
        code, d = self.cli("check-load", "--project", root, "--confirm", "red suit visible in lobby")
        m = json.loads((Path(root) / "mrforge.json").read_text(encoding="utf-8"))
        self.assertEqual(m["evidence"][0]["tier"], "load")
