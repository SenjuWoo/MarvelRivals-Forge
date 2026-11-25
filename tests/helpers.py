"""Shared fixtures: temp forge home, synthetic game tree, tool shims, CLI runner. Everything offline."""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SHIMS = Path(__file__).resolve().parent / "shims"

SKIN = "1061303"
CL = 4042190
BASE = f"Marvel/Content/Marvel/Characters/1061/{SKIN}"


def _p(kind, cls, value):
    return {"$type": f"UAssetAPI.PropertyTypes.{kind}.{cls}, UAssetAPI", "Name": "ParameterValue", "Value": value}


def _entry(struct, name, pv, zero_header=False):
    e = {"$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI", "StructType": struct, "Name": "0",
         "OriginalStructHeader": {"ZeroMask": [False, True, False]} if zero_header else None,
         "Value": [{"StructType": "MaterialParameterInfo", "Name": "ParameterInfo",
                    "Value": [{"Name": "Name", "Value": name}, {"Name": "Association", "Value": "GlobalParameter"},
                              {"Name": "Index", "Value": -1}]},
                   pv,
                   {"StructType": "Guid", "Name": "ExpressionGUID", "Value": []}]}
    return e


def material_json(skin=SKIN):
    color = {"$type": "UAssetAPI.UnrealTypes.FLinearColor, UAssetAPI", "R": 1.0, "G": 1.0, "B": 1.0, "A": "+0"}
    return {
        "$type": "UAssetAPI.UAsset, UAssetAPI",
        "Imports": [
            {"ObjectName": "MaterialInstanceConstant", "OuterIndex": -5, "ClassName": "Class"},
            {"ObjectName": "M_1061001_Skin", "OuterIndex": -3, "ClassName": "Material"},
            {"ObjectName": "/Game/Marvel/Characters/1061/1061001/Materials/M_1061001_Skin", "OuterIndex": 0, "ClassName": "Package"},
            {"ObjectName": f"/Game/Marvel/Characters/1061/{skin}/Textures/T_{skin}_Body_01_D", "OuterIndex": 0, "ClassName": "Package"},
            {"ObjectName": "/Script/Engine", "OuterIndex": 0, "ClassName": "Package"},
            {"ObjectName": f"T_{skin}_Body_01_D", "OuterIndex": -4, "ClassName": "Texture2D"},
        ],
        "Exports": [{"ObjectName": f"MI_{skin}_Body_01", "Data": [
            {"Name": "Parent", "Value": -2},
            {"Name": "ScalarParameterValues", "Value": [
                _entry("ScalarParameterValue", "AOIntensity", {"Name": "ParameterValue", "Value": "+0"}),
                _entry("ScalarParameterValue", "Roughness", {"Name": "ParameterValue", "Value": 0.5})]},
            {"Name": "VectorParameterValues", "Value": [
                _entry("VectorParameterValue", "BaseTint", {"StructType": "LinearColor", "Name": "ParameterValue",
                                                            "Value": [{"Name": "ParameterValue", "Value": color}]}),
                _entry("VectorParameterValue", "BackRimColor", {"StructType": "LinearColor", "Name": "ParameterValue",
                                                                "IsZero": True, "Value": []}, zero_header=True)]},
            {"Name": "TextureParameterValues", "Value": [
                _entry("TextureParameterValue", "BaseColor", {"Name": "ParameterValue", "Value": -6})]},
        ]}],
    }


def _hdr():
    return {"$type": "UAssetAPI.Unversioned.FUnversionedHeader, UAssetAPI", "ZeroMask": [False, True]}


def _f(name, value):
    return {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": name, "Value": value,
            "IsZero": False}


def _struct(name, struct, values, header=True):
    return {"$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI", "StructType": struct, "Name": name,
            "OriginalStructHeader": _hdr() if header else None, "Value": values}


def _bone(name, bone):
    return _struct(name, "BoneReference", [{"Name": "BoneName", "Value": bone}])


def kawaii_chain(root, idx=0, damping=0.35):
    """One KawaiiPhysicsChain element shaped like the captured Post_1061303_Physics data."""
    bs = _struct("BoneSettings", "BoneSettings", [
        _bone("RootBone", root), {"Name": "ExcludeBones", "Value": []},
        {"Name": "AdditionalRootBones", "Value": [_struct("0", "KawaiiPhysicsRootBoneSetting", [_bone("RootBone", root + "_B")])]},
        _f("DummyBoneLength", "+0")])
    ps = _struct("PhysicsSettings", "KawaiiPhysicsSettings", [
        _f("Damping", damping), _f("Stiffness", 0.05), _f("WorldDampingLocation", 0.98), _f("WorldDampingRotation", 0.8),
        _f("Radius", 3.0), _f("LimitAngle", 40.0), _f("LimitLinear", "+0"), _f("GravityScale", 1.0)])
    phs = _struct("PhysicsSettings", "KawaiiPhysicsChainPhysicsSettings", [
        ps, {"Name": "bUseCurve", "Value": True}, _f("TeleportDistanceThreshold", 300.0),
        _f("TeleportRotationThreshold", 10.0)])
    return _struct(str(idx), "KawaiiPhysicsChain", [bs, phs])


def _node(name, struct, link_field, link, extra=None):
    pose = _struct(link_field, "ComponentSpacePoseLink" if "Kawaii" in struct or "Constraint" in struct else "PoseLink",
                   [{"Name": "LinkID", "Value": link}])
    return _struct(name, struct, [pose] + (extra or []))


def physics_json(with_kawaii=True):
    """CDO in LinkID order: input(2) -> rivet(4) -> Kawaii(3) -> Kawaii_1(0) -> Root(1)."""
    k1 = _node("AnimGraphNode_KawaiiPhysics_1", "AnimNode_KawaiiPhysics", "ComponentPose", 3,
               [{"Name": "Chains", "Value": [kawaii_chain("Collar_A1")]}])
    k0 = _node("AnimGraphNode_KawaiiPhysics", "AnimNode_KawaiiPhysics", "ComponentPose", 4,
               [{"Name": "Chains", "Value": [kawaii_chain("hair_A1"), kawaii_chain("hair_B1", 1)]}])
    if not with_kawaii:
        k1 = _node("AnimGraphNode_Constraint_1", "AnimNode_Constraint", "ComponentPose", 3)
        k0 = _node("AnimGraphNode_Constraint_2", "AnimNode_Constraint", "ComponentPose", 4)
    cdo = [{"Name": "UberGraphFrame", "StructType": "PointerToUberGraphFrame"}, k1,
           _node("AnimGraphNode_Root", "AnimNode_Root", "Result", 0),
           _node("AnimGraphNode_LinkedInputPose", "AnimNode_LinkedInputPose", "InputPose", -1),
           k0, _node("RivetConstraint", "AnimNode_Constraint", "ComponentPose", 2)]
    # UberGraphFrame is not an anim node: LinkIDs index the AnimNode_* properties only.
    return {"$type": "UAssetAPI.UAsset, UAssetAPI", "NameMap": ["Collar_A1", "hair_A1", "hair_B1", "L_Breast_01_Jnt"],
            "Exports": [{"ObjectName": "Post_X_Physics_C", "Data": []},
                        {"ObjectName": "Default__Post_X_Physics_C", "Data": cdo}]}


def vanilla_packages():
    tex = lambda fmt, mips, w=64, color=(200, 120, 100): {"kind": "texture", "fmt": fmt, "mips": mips, "w": w, "h": w,  # noqa: E731
                                                          "color": list(color)}
    return {
        f"{BASE}/Textures/T_{SKIN}_Body_01_D.uasset": tex("PF_DXT1", 7),
        f"{BASE}/Textures/T_{SKIN}_Body_01_N.uasset": tex("PF_BC5", 7, color=(128, 128, 255)),
        f"{BASE}/Textures/T_{SKIN}_Body_01_ORM.uasset": tex("PF_DXT1", 6, 32),
        f"{BASE}/Materials/MI_{SKIN}_Body_01.uasset": {"kind": "material", "json": material_json()},
        f"{BASE}/Materials/Lobby/MI_{SKIN}_Body_01.uasset": {"kind": "material", "json": material_json()},
        f"{BASE}/Meshes/SK_1061_{SKIN}.uasset": {"kind": "mesh"},
        f"{BASE}/Meshes/SK_1061_{SKIN}_Lobby.uasset": {"kind": "mesh"},
        f"{BASE}/Post_{SKIN}_Physics.uasset": {"kind": "json", "json": physics_json()},
        f"{BASE}/Post_{SKIN}_Lobby_Physics.uasset": {"kind": "json", "json": physics_json(with_kawaii=False)},
        "Marvel/Content/Marvel/Characters/1061/1061001/Textures/T_1061001_Hair01_N.uasset": tex("PF_BC5", 7),
    }


def make_game(root: Path, changelist: int = CL, loader: bool = True) -> Path:
    paks = root / "MarvelGame" / "Marvel" / "Content" / "Paks"
    (paks / "~mods").mkdir(parents=True, exist_ok=True)
    (root / "MarvelGame" / "version.json").write_text(json.dumps({"version": f"1.1.{changelist}", "changelist": changelist}),
                                                      encoding="utf-8")
    (paks / "fake_vanilla.json").write_text(json.dumps({"packages": vanilla_packages()}), encoding="utf-8")
    w = root / "MarvelGame" / "Marvel" / "Binaries" / "Win64"
    (w / "plugins").mkdir(parents=True, exist_ok=True)
    if loader:
        (w / "dsound.dll").write_bytes(b"x")
        (w / "plugins" / "MarvelRivalsUTOCSignatureBypass.asi").write_bytes(b"x")
    return root


def fake_mod(mods_dir: Path, folder: str, name: str, packages: list[str], flags=("Compressed", "Indexed")) -> Path:
    d = mods_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.utoc").write_text(json.dumps({"flags": list(flags), "packages": packages, "files": {}}), encoding="utf-8")
    (d / f"{name}.ucas").write_bytes(b"u")
    (d / f"{name}.pak").write_bytes(b"p")
    return d


class ForgeCase(unittest.TestCase):
    """Temp MRFORGE_HOME + synthetic game + shims for both tools."""

    with_game = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mrf test (x)! "))
        self._env = dict(os.environ)
        os.environ["MRFORGE_HOME"] = str(self.tmp / "home")
        os.environ["MRFORGE_SHIM_UASSETTOOL"] = str(SHIMS / "uassettool.py")
        os.environ["MRFORGE_SHIM_RETOC_RIVALS_CLI"] = str(SHIMS / "retoc.py")
        os.environ["MRFORGE_LOG_DIR"] = str(self.tmp / "logs")
        os.environ.pop("MRFORGE_GAME", None)
        os.environ.pop("MRFORGE_PROJECT", None)
        from mrforge import index
        index._LOADED.clear()
        if self.with_game:
            self.game = make_game(self.tmp / "game")
            os.environ["MRFORGE_GAME"] = str(self.game)
            self.mods_dir = self.game / "MarvelGame" / "Marvel" / "Content" / "Paks" / "~mods"
            self.paks = self.mods_dir.parent

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seed_usmap(self, changelist: int = CL):
        from mrforge.home import home
        from mrforge.util import save_json, sha256_bytes
        d = home() / "cache" / "usmap"
        name = f"5.3.2-{changelist}+++depot_marvel+S11.0_release-Marvel.usmap"
        data = b"USMAP" * 400
        (d / name).write_bytes(data)
        save_json(d / "index.json", {name: {"build": changelist, "season": "11.0", "sha256": sha256_bytes(data)}})
        return d / name

    def ready(self):
        """usmap + index for the synthetic game."""
        self.seed_usmap()
        from mrforge.index import build
        build(self.paks, CL)

    def cli(self, *argv, cwd=None):
        from mrforge.cli import main
        buf = io.StringIO()
        old = os.getcwd()
        try:
            if cwd:
                os.chdir(cwd)
            with redirect_stdout(buf):
                code = main(list(argv))
        finally:
            os.chdir(old)
        return code, json.loads(buf.getvalue())
