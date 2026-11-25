"""Knowledge, router, catalog, index, mods, project, doctor."""
import json
import os
import re

from helpers import CL, SKIN, ForgeCase, fake_mod

from mrforge.util import ForgeError, KNOWLEDGE_DIR


class Knowledge(ForgeCase):
    with_game = False

    def test_all_knowledge_json_parses(self):
        for p in KNOWLEDGE_DIR.glob("*.json"):
            json.loads(p.read_text(encoding="utf-8"))

    def test_facts_have_tier_and_source(self):
        from mrforge.knowledge import facts
        fs = facts()
        self.assertGreaterEqual(len(fs), 20)
        for f in fs:
            self.assertIn(f["tier"], ("verified-local", "upstream-doc", "reported"))
            self.assertTrue(f["source"] and f["id"] and f["statement"])
        self.assertEqual(len({f["id"] for f in fs}), len(fs))

    def test_routes_name_existing_commands(self):
        from mrforge.cli import _walk, parser
        from mrforge.knowledge import routes
        top = {c["command"].split()[0] for c in _walk(parser(), "")}
        v01 = [r for r in routes() if r.get("release") == "v0.1"]
        self.assertTrue(v01)
        for r in v01:
            for c in r["commands"]:
                for m in re.finditer(r"mrforge ([a-z-]+)", c):
                    self.assertIn(m.group(1), top, f"{r['id']}: {c}")

    def test_error_signatures_compile(self):
        from mrforge.knowledge import errors
        for s in errors():
            re.compile(s["pattern"])

    def test_docs_exist_for_routes(self):
        from mrforge.knowledge import docs, routes
        have = set(docs())
        for r in routes():
            for d in r.get("docs", []):
                self.assertIn(d, have, f"route {r['id']} names missing doc {d}")

    def test_plan_table(self):
        from mrforge.knowledge import plan
        table = {
            "make Black Cat's suit red": "texture",
            "recolor the gloves to gold": "texture",
            "add a logo on the chest": "texture",
            "change her skin tone darker": "texture",
            "retexture the cape with a camo pattern": "texture",
            "make the eyes glow stronger": "material",
            "less shiny, more matte roughness": "material",
            "change the emissive intensity": "material",
            "new body shape, bigger proportions": "mesh",
            "swap outfit to another model": "mesh",
            "remove the jacket mesh": "mesh",
            "add jiggle physics": "physics",
            "more cloth sway on the skirt physics": "physics",
            "make her boobs bounce": "physics",
            "softer hair physics": "physics",
            "replace voice lines": "sound",
            "custom gunshot sound for the primary fire": "sound",
            "new hud icon": "unsupported",
            "change ability cooldown": "unsupported",
        }
        bad = {req: plan(req)["route"] for req, want in table.items() if plan(req)["route"] != want}
        self.assertEqual(bad, {})
        both = plan("make her chest bigger and add jiggle")
        self.assertEqual(both["combine"]["routes"], ["mesh", "physics"])
        self.assertNotIn("combine", plan("make the eyes glow stronger"))
        self.assertGreaterEqual(len(table), 12)


class Catalog(ForgeCase):
    with_game = False

    def test_hero_id_rule_every_row(self):
        from mrforge.catalog import rows
        rs = rows()
        self.assertGreater(len(rs), 300)
        for r in rs:
            self.assertRegex(r["skin_id"], r"^\d{7}$")
            self.assertEqual(r["hero_id"], r["skin_id"][:4])

    def test_lookups(self):
        from mrforge.catalog import find_hero, find_skin, resolve_skin, rows, skins_of
        r0 = rows()[0]
        self.assertEqual(resolve_skin(r0["skin_id"])["skin_id"], r0["skin_id"])
        self.assertTrue(find_hero(r0["hero"]))
        self.assertTrue(find_hero(r0["hero_id"]))
        self.assertTrue(skins_of(r0["hero"]))
        self.assertTrue(find_skin(r0["skin"]))
        self.assertEqual(resolve_skin("9999001")["note"], "not in the name table")
        with self.assertRaises(ForgeError):
            resolve_skin("zzzz no such skin zzzz")

    def test_convert(self):
        from mrforge.catalog import convert
        out = convert([{"name": "A", "id": "1001001", "skinid": "1001300", "skin_name": "S"},
                       {"name": "A", "id": "1001001", "skinid": "1001300", "skin_name": "dup"},
                       {"name": "B", "skinid": "bad"}])
        self.assertEqual(out, [{"skin_id": "1001300", "hero_id": "1001", "hero": "A", "skin": "S"}])


class Index(ForgeCase):
    def test_parse_listing_real_format(self):
        from mrforge.index import parse_listing
        text = ("[ListIoStore] Detected obfuscated container\n=== pakchunkCharacter-Windows.utoc ===\n"
                "  ../../../Marvel/Content/Marvel/Characters/1061/1061303/Textures/T_1061303_Body_01_D.uasset [.ubulk]  (export=3,792b bulk=696,320b)\n"
                "  ../../../Marvel/Content/Marvel/Characters/1061/1061303/Materials/MI_1061303_Body_01.uasset [no bulk]  (export=50,538b)\n")
        d = parse_listing(text)
        self.assertEqual(d["containers"], ["pakchunkCharacter-Windows.utoc"])
        p = d["packages"]["Marvel/Content/Marvel/Characters/1061/1061303/Textures/T_1061303_Body_01_D.uasset"]
        self.assertEqual(p, [0, 1, 3792, 696320])

    def test_build_and_skin_packages(self):
        from mrforge.index import build, classify, exists, load, skin_packages
        build(self.paks, CL)
        idx = load(CL)
        pk = skin_packages(idx, SKIN)
        self.assertEqual(len(pk), 9)  # incl. the lobby post-process asset
        self.assertTrue(exists(idx, f"/Game/Marvel/Characters/1061/{SKIN}/Textures/T_{SKIN}_Body_01_D"))
        self.assertEqual(classify(f"x/{SKIN}/Post_{SKIN}_Physics.uasset"), "physics")
        self.assertEqual(classify("x/Meshes/SK_1061_1061303_Skeleton.uasset"), "skeleton")
        self.assertEqual(classify("x/Meshes/SK_1061_1061303.uasset"), "mesh")

    def test_index_missing_named(self):
        from mrforge.index import load
        with self.assertRaises(ForgeError) as cm:
            load(123)
        self.assertEqual(cm.exception.code, "INDEX_MISSING")


class Mods(ForgeCase):
    def test_parse_info_and_filters(self):
        from mrforge.mods import parse_filters, parse_info
        self.assertEqual(parse_info("  container_flags: EIoContainerFlags(Compressed | Indexed)\n  packages: 7\n"),
                         {"flags": ["Compressed", "Indexed"], "package_count": 7})
        self.assertTrue(parse_info("type: legacy-pak\nencrypted index: true\n")["encrypted_index"])
        self.assertEqual(parse_filters("../../../Marvel/Content/a.uasset\n../../../Marvel/Content/b.uasset\n"),
                         ["Marvel/Content/a.uasset", "Marvel/Content/b.uasset"])

    def test_scan_flags_and_conflicts(self):
        from mrforge.mods import conflicts, scan
        pkg = f"Marvel/Content/Marvel/Characters/1061/{SKIN}/Meshes/SK_1061_{SKIN}.uasset"
        fake_mod(self.mods_dir, "AAA-one", "One_9999999_P", [pkg])
        fake_mod(self.mods_dir, "AAB-two", "Two_9999999_P", [pkg, "Marvel/Content/x.uasset"], flags=("Encrypted", "Indexed"))
        mods = scan(self.mods_dir)
        self.assertEqual(len(mods), 2)
        self.assertEqual([m["name"] for m in mods if m.get("flags_bad")], ["Two_9999999_P"])
        c = conflicts(mods)
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["mods"]), 2)
        mods2 = scan(self.mods_dir)  # cached path
        self.assertEqual(mods2[0]["packages"], [pkg])


class Project(ForgeCase):
    def test_scaffold_bump_slug(self):
        from mrforge import project as P
        from mrforge.util import pak_name, slugify
        self.assertEqual(slugify("  Red Cat: v2 (final)! "), "red-cat-v2-final")
        self.assertEqual(pak_name("red cat: v2"), "RedCatV2")
        skin = {"skin_id": SKIN, "hero_id": "1061", "hero": "H", "skin": "S"}
        root = P.new("Red Cat: v2", skin, ["texture", "material"], CL, out=str(self.tmp / "p (1)"))
        m = P.manifest(root)
        self.assertEqual((m["id"], m["pak_name"], m["version"]), ("red-cat-v2", "RedCatV2", "0.1.0"))
        for d in P.LAYOUT:
            self.assertTrue((root / d).is_dir())
        self.assertEqual(P.bump(root, "minor", "more red"), {"old": "0.1.0", "new": "0.2.0"})
        self.assertIn("## 0.2.0", (root / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertEqual(P.find(str(root)), root.resolve())
        with self.assertRaises(ForgeError):
            P.new("Red Cat: v2", skin, ["texture"], CL, out=str(root))
        with self.assertRaises(ForgeError):
            P.new("x", skin, ["animation"], CL, out=str(self.tmp / "q"))


class Doctor(ForgeCase):
    def test_failures_named(self):
        from mrforge.doctor import run_doctor
        d, ok = run_doctor()
        ids = {c["id"]: c["status"] for s in d["sections"].values() for c in s}
        self.assertEqual(ids["game_found"], "ok")
        self.assertEqual(ids["usmap"], "fail")  # nothing synced yet
        self.assertEqual(ids["index"], "warn")
        routes = {r["route"]: r["status"] for r in d["routes"]}
        self.assertEqual(routes["texture"], "unavailable")  # no usmap
        self.assertEqual(routes["physics"], "unavailable")

    def test_ok_with_data(self):
        from mrforge.doctor import run_doctor
        self.ready()
        d, ok = run_doctor()
        routes = {r["route"]: r["status"] for r in d["routes"]}
        self.assertEqual(routes["texture"], "available")
        tool_ids = {c["id"]: c["status"] for c in d["sections"]["toolchain"]}
        self.assertEqual(tool_ids["uassettool"], "ok")

    def test_missing_game(self):
        from mrforge.doctor import run_doctor
        os.environ["MRFORGE_GAME"] = str(self.tmp / "nothing")
        d, ok = run_doctor()
        self.assertFalse(ok)
        self.assertEqual(d["sections"]["game"][0]["status"], "fail")
