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
        f"{BASE}/Post_{SKIN}_Physics.uasset": {"kind": "physics"},
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
