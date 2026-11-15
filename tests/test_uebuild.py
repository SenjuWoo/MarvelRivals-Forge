"""Mesh build helpers that do not need Unreal: reference parsing from captured tool output, project files."""
import json
import unittest

from helpers import ForgeCase

MESH_INFO = """=== Skeletal Mesh Analysis: SK_1061_1061303.uasset ===
  === Materials (3) ===
    [0] MaterialInterface: -3
        SlotName: MI_1061303_Head
        ImportedSlotName: 01 - Default
        GameplayTags: 1
          - MaterialTag.FX1
    [1] MaterialInterface: -4
        SlotName: MI_1061303_Equip_05
        ImportedSlotName: 01 - Default
        GameplayTags: 2
          - MaterialTag.FX1
          - MaterialTag.Cape
    [2] MaterialInterface: -4
        SlotName: MI_1061303_Equip_03
        ImportedSlotName: 01 - Default
        GameplayTags: 0
  === Reference Skeleton ===
    Bone Count: 481
"""

DUMP = """=== Imports ===
  [0] Post_1061303_Physics_C
  [1] SkeletalMesh
  [2] MI_1061303_Head
  [3] MI_1061303_Equip_05
  [4] /Game/Marvel/Characters/1061/1061303/Post_1061303_Physics
  [5] /Game/Marvel/Characters/1061/1061303/Materials/MI_1061303_Head
  [6] /Game/Marvel/Characters/1061/1061303/Materials/MI_1061303_Equip_05
  [7] /Game/Marvel/Characters/1061/1061001/Meshes/SK_1061_1061001_PhysicsAsset
  [8] /Game/Marvel/Characters/1061/1061001/Meshes/SK_1061_1061001_Skeleton
  [9] /Script/Engine
"""


class Refs(unittest.TestCase):
    def test_parse_refs(self):
        from mrforge.uebuild import parse_refs
        r = parse_refs(MESH_INFO, DUMP)
        self.assertEqual(r["skeleton"], "/Game/Marvel/Characters/1061/1061001/Meshes/SK_1061_1061001_Skeleton")
        self.assertEqual(r["physics"], "/Game/Marvel/Characters/1061/1061001/Meshes/SK_1061_1061001_PhysicsAsset")
        self.assertEqual(r["postprocess"], "/Game/Marvel/Characters/1061/1061303/Post_1061303_Physics")
        self.assertEqual([m["slot"] for m in r["materials"]], ["MI_1061303_Head", "MI_1061303_Equip_05", "MI_1061303_Equip_03"])
        # Two slots can share one material instance; the slot name is not the material name.
        self.assertEqual(r["materials"][2]["path"], "/Game/Marvel/Characters/1061/1061303/Materials/MI_1061303_Equip_05")
        self.assertEqual(r["materials"][1]["tags"], ["MaterialTag.FX1", "MaterialTag.Cape"])


class Project(ForgeCase):
    with_game = False

    def test_init_project_files(self):
        from mrforge import uebuild
        from mrforge.home import home
        plug = home() / "tools" / "rivals-mesh-material-manager" / "v1.2.0" / "RivalsMeshMaterialManager"
        dll = plug / "Binaries" / "Win64" / "UnrealEditor-RivalsMeshMaterialManager.dll"
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"dll")
        (plug / "RivalsMeshMaterialManager.uplugin").write_text("{}", encoding="utf-8")
        from mrforge import tools as T
        orig = T.require
        T.require = lambda name: T.entry(name)  # hash of the fake DLL is irrelevant here
        try:
            d = uebuild.init_project(["MaterialTag.特效专用1", "MaterialTag.X"])
        finally:
            T.require = orig
        up = json.loads((d / "Marvel.uproject").read_text(encoding="utf-8"))
        self.assertIn("RivalsMeshMaterialManager", [p["Name"] for p in up["Plugins"]])
        self.assertIn("bUseIoStore=False", (d / "Config" / "DefaultGame.ini").read_text(encoding="utf-8"))
        tags = (d / "Config" / "DefaultGameplayTags.ini").read_bytes()
        self.assertTrue(tags.startswith(b"\xff\xfe"))  # UTF-16 LE BOM: Unreal reads BOM-less ini as ANSI
        self.assertIn("MaterialTag.特效专用1", tags.decode("utf-16"))
        self.assertTrue((d / "Plugins" / "RivalsMeshMaterialManager" / "Binaries" / "Win64" /
                         "UnrealEditor-RivalsMeshMaterialManager.dll").is_file())
