"""Mesh route: MCP client against a fake server, vanilla view cleanup, export copying, vanilla comparison."""
import json
import os
from pathlib import Path

from helpers import SHIMS, SKIN, ForgeCase

from mrforge.util import ForgeError


def _summary(slots, bones, groups=None):
    bl = [{"name": b, "parent": p} for b, p in bones]
    import hashlib
    return {"meshes": [{"name": "m", "vertices": 10, "triangles": 5, "material_slots": slots,
                        "vertex_groups": groups if groups is not None else [b for b, _ in bones]}],
            "armatures": [{"name": "a", "bone_count": len(bl), "bones": bl,
                           "hierarchy_sha256": hashlib.sha256(json.dumps(bl).encode()).hexdigest()}]}


class MeshExport(ForgeCase):
    def setUp(self):
        super().setUp()
        self.ready()
        os.environ["MRFORGE_SHIM_FMODEL_MCP"] = str(SHIMS / "fake_mcp.py")
        (self.paks / "pakchunkCharacter-Windows.utoc").write_bytes(b"u")
        (self.paks / "pakchunkCharacter-Windows.ucas").write_bytes(b"c")
        from mrforge.home import home
        from mrforge.util import save_json
        save_json(home() / "keys.json", {"mainKey": "0xKEY"})
        code, d = self.cli("new", "Mesh", "--skin", SKIN, "--kind", "mesh", "--out", str(self.tmp / "m"))
        self.root = Path(d["data"]["project"])

    def test_export_copies_and_cleans_view(self):
        code, d = self.cli("mesh", "export", "--lobby", "--project", str(self.root))
        self.assertEqual(code, 0, d)
        self.assertEqual(len(d["data"]["meshes"]), 2)
        um = self.root / "work" / "mesh" / "vanilla" / d["data"]["meshes"][0]["uemodel"]
        self.assertEqual(um.read_bytes(), b"UEMODEL")
        from mrforge.mesh import leftover_views
        self.assertEqual(leftover_views(self.game), [])

    def test_non_vanilla_archive_refused(self):
        os.environ["FAKE_MCP_ARCHIVE"] = "SomeMod_9999999_P.utoc"
        try:
            code, d = self.cli("mesh", "export", "--project", str(self.root))
        finally:
            os.environ.pop("FAKE_MCP_ARCHIVE")
        self.assertEqual(d["errors"][0]["code"], "VANILLA_VIEW_LEAK")
        from mrforge.mesh import leftover_views
        self.assertEqual(leftover_views(self.game), [])

    def test_missing_key(self):
        from mrforge.home import home
        (home() / "keys.json").unlink()
        code, d = self.cli("mesh", "export", "--project", str(self.root))
        self.assertEqual(d["errors"][0]["code"], "AES_KEY_MISSING")


class MeshCompare(ForgeCase):
    with_game = False

    def test_compare(self):
        from mrforge.mesh import compare
        bones = [("root", None), ("pelvis", "root"), ("spine", "pelvis")]
        v = _summary(["MI_A", "MI_B"], bones)
        self.assertEqual(compare(v, _summary(["MI_A", "MI_B"], bones)), [])
        self.assertTrue(compare(v, _summary(["MI_B", "MI_A"], bones)))  # order matters
        self.assertTrue(compare(v, _summary(["MI_A", "MI_B"], [("root", None), ("pelvis", "root"), ("spine", "root")])))
        self.assertTrue(compare(v, _summary(["MI_A", "MI_B"], bones, groups=["root", "Cube"])))
