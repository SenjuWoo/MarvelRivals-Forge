"""Mesh build through Unreal Engine 5.3.2: vanilla refs -> UE import with placeholders -> cook -> collect the cooked
mesh only (packing happens in build.py, decision D26).

Project: .mrforge/ue/Marvel (named exactly Marvel so cooked paths are Marvel/Content/...), pak/IoStore off.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from . import project as P
from . import tools as T
from .game import find_game, layout, version
from .home import home
from .sync import require_usmap
from .ue import detect
from .uat import extract_vanilla, parse_mesh_info, pattern_for
from .util import EnvError, ForgeError, PKG_DIR, fwd, run, save_json

UPROJECT = {
    "FileVersion": 3, "EngineAssociation": "5.3", "Category": "",
    "Description": "MarvelRivals-Forge cook project (generated)",
    "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}, {"Name": "EditorScriptingUtilities", "Enabled": True}],
}
ENGINE_INI = "[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap=/Engine/Maps/Entry\nEditorStartupMap=/Engine/Maps/Entry\n"
GAME_INI = ("[/Script/UnrealEd.ProjectPackagingSettings]\nbUseIoStore=False\nbShareMaterialShaderCode=False\n"
            "bUsePakFile=False\n+DirectoriesToAlwaysCook=(Path=\"/Game/Marvel\")\n")


def project_dir() -> Path:
    return home() / "ue" / "Marvel"


def init_project(tags: list[str] | None = None, anim: bool = False) -> Path:
    """Generated cook project. anim=True also enables KawaiiPhysicsRivals and MrforgeAnimTools (built by uepost)."""
    d = project_dir()
    (d / "Config").mkdir(parents=True, exist_ok=True)
    (d / "Content").mkdir(exist_ok=True)
    up = json.loads(json.dumps(UPROJECT))
    plug = T.entry("rivals-mesh-material-manager")
    src = T.tool_dir(T.require("rivals-mesh-material-manager")) / "RivalsMeshMaterialManager"
    dst = d / "Plugins" / "RivalsMeshMaterialManager"
    if not (dst / plug["exe"].split("/", 1)[1]).is_file():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    up["Plugins"].append({"Name": "RivalsMeshMaterialManager", "Enabled": True})
    for name in ("KawaiiPhysics", "MrforgeAnimTools"):
        # Project plugins load by default when present; list them explicitly either way so a mesh-only cook never
        # depends on plugins that may not be built on this machine.
        if (d / "Plugins" / name).is_dir():
            up["Plugins"].append({"Name": name, "Enabled": bool(anim)})
    (d / "Marvel.uproject").write_text(json.dumps(up, indent=2), encoding="utf-8")
    (d / "Config" / "DefaultEngine.ini").write_text(ENGINE_INI, encoding="utf-8")
    (d / "Config" / "DefaultGame.ini").write_text(GAME_INI, encoding="utf-8")
    # The game's material tags (often Chinese) must exist as gameplay tags or FGameplayTag values are invalid.
    # UTF-16 with BOM: Unreal reads ini files without a BOM as ANSI.
    lines = ["[/Script/GameplayTags.GameplayTagsSettings]", "ImportTagsFromConfig=True"]
    lines += [f'+GameplayTagList=(Tag="{t}",DevComment="")' for t in sorted(set(tags or []))]
    crlf = "\r\n"
    (d / "Config" / "DefaultGameplayTags.ini").write_text(crlf.join(lines) + crlf, encoding="utf-16")
    return d


def editor() -> Path:
    u = detect()
    if not u["found"]:
        raise EnvError("UE_532_MISSING", "Unreal Engine 5.3.2 not found", "install it, or mrforge setup --ue <folder>")
    return Path(u["editor_cmd"])


def run_ue(args: list[str], timeout: float = 3600, env: dict | None = None) -> dict:
    uproj = project_dir() / "Marvel.uproject"
    return run([str(editor()), str(uproj), *args, "-unattended", "-nosplash", "-NoSound", "-stdout",
                "-FullStdOutLogOutput", "-nullrhi"], timeout=timeout, env=env)


def vanilla_refs(raw_mesh: Path, usmap: Path) -> dict:
    """Slot -> material package, skeleton, physics asset, post-process AnimBP, from the vanilla cooked mesh.

    skeletal_mesh_info prints `[i] MaterialInterface: -18` per slot; -18 is the 0-based import 17 in `dump`.
    """
    text = T.run_tool("uassettool", ["skeletal_mesh_info", fwd(raw_mesh), fwd(usmap)], timeout=600)["stdout"]
    dump = T.run_tool("uassettool", ["dump", fwd(raw_mesh), fwd(usmap)], timeout=600)["stdout"]
    return parse_refs(text, dump)


def parse_refs(text: str, dump: str) -> dict:
    """Pure part of vanilla_refs: skeletal_mesh_info text + dump text -> refs."""
    info = parse_mesh_info(text)
    by_index = {int(i): int(r) for i, r in re.findall(r"\[(\d+)\] MaterialInterface: (-?\d+)", text)}
    imports, sect = [], False
    for line in dump.splitlines():
        if line.startswith("=== Imports"):
            sect = True
            continue
        if sect:
            mt = re.match(r"^\s+\[(\d+)\] (.+?)\s*$", line)
            if mt:
                imports.append(mt.group(2))
            elif line.startswith("==="):
                break
    pkgs = [i for i in imports if i.startswith("/Game/")]

    def pkg_of(obj: str | None) -> str | None:
        return next((p for p in pkgs if p.rsplit("/", 1)[-1] == obj), None) if obj else None

    mats = []
    for s in info["materials"]:
        r = by_index.get(s["index"])
        obj = imports[-r - 1] if r is not None and r < 0 and -r - 1 < len(imports) else None
        mats.append({"slot": s["slot"], "tags": s["tags"], "path": pkg_of(obj)})
    return {"materials": mats,
            "skeleton": next((p for p in pkgs if p.endswith("_Skeleton")), None),
            "physics": next((p for p in pkgs if p.endswith("_PhysicsAsset")), None),
            "postprocess": next((p for p in pkgs if p.rsplit("/", 1)[-1].startswith("Post_") and p.endswith("_Physics")), None)}


def _cook_one(root: Path, groot: Path, pkg: str, usmap: Path, stage: Path) -> dict:
    """Import one edited mesh at its vanilla path with placeholders, cook, copy the cooked mesh into stage."""
    from .mesh import run_blender
    blend = root / "work" / "mesh" / (Path(pkg).stem + ".blend")
    if not blend.is_file():
        raise ForgeError("NO_BLEND", f"{blend.name} missing", "mrforge mesh blend")
    raw = root / "vanilla" / "raw"
    extract_vanilla(layout(groot)["paks_dir"], raw, [pattern_for(pkg)])
    refs = vanilla_refs(raw / pkg, usmap)
    missing = [x["slot"] for x in refs["materials"] if not x["path"]]
    if missing or not refs["skeleton"]:
        raise ForgeError("MESH_REFS_UNRESOLVED", f"skeleton={refs['skeleton']} unresolved slots={missing}", "report this mesh")
    stem = Path(pkg).stem
    names = root / "build" / f"{stem}.slot_names.json"
    save_json(names, [x["slot"] for x in refs["materials"]])
    fbx = root / "build" / "fbx" / f"{stem}.game-slots.fbx"
    fbx.parent.mkdir(parents=True, exist_ok=True)
    run_blender(["fbx", str(blend), str(fbx), str(names)])
    d = init_project([t for x in refs["materials"] for t in x["tags"]])
    # Fresh content per mesh: placeholders of a previous mesh (shared skeleton paths) must not leak into this cook.
    for sub in ("Content/Marvel", "Saved/Cooked"):
        shutil.rmtree(d / sub, ignore_errors=True)
    job = {"fbx": str(fbx.resolve()), "mesh_path": "/Game/" + pkg[len("Marvel/Content/"):-len(".uasset")],
           "skeleton_path": refs["skeleton"], "physics_path": refs["physics"], "postprocess_path": refs["postprocess"],
           "materials": refs["materials"]}
    jp = root / "build" / f"{stem}.ue_job.json"
    save_json(jp, job)
    r = run_ue(["-run=pythonscript", f"-script={PKG_DIR / 'unreal' / 'import_mesh.py'}"], env={"MRFORGE_UE_JOB": str(jp)})
    rep = next((json.loads(ln.split("MRFORGE_JSON:", 1)[1]) for ln in r["stdout"].splitlines() if "MRFORGE_JSON:" in ln), None)
    if not rep or rep.get("error"):
        raise ForgeError("UE_IMPORT_FAILED", (rep or {}).get("error") or r["stdout"][-800:], "see .mrforge/ue/Marvel/Saved/Logs")
    if not rep.get("slot_order_matches"):
        raise ForgeError("UE_SLOT_ORDER", f"imported slots {rep.get('slots')} != vanilla {rep.get('vanilla_slots')}",
                         "keep material slots in vanilla order in Blender (mrforge mesh check)")
    # Versioned (tagged) cook on purpose: an -unversioned cook writes properties by stock UE's class schema, which
    # differs from the game's, so the game's mappings misread it (verified). UAssetTool converts the tagged cook to
    # the game's unversioned layout and injects FSkeletalMaterial gameplay tags while packing.
    c = run_ue(["-run=cook", "-targetplatform=Windows", "-iterate=false"], timeout=7200)
    cooked_root = d / "Saved" / "Cooked" / "Windows" / "Marvel" / "Content"
    rel = pkg[len("Marvel/Content/"):-len(".uasset")]
    cooked = [cooked_root / (rel + ext) for ext in (".uasset", ".uexp", ".ubulk")]
    if not cooked[0].is_file():
        errs = [ln for ln in c["stdout"].splitlines() if "Error" in ln][-15:]
        raise ForgeError("UE_COOK_FAILED", " | ".join(errs) or c["stdout"][-800:], "see .mrforge/ue/Marvel/Saved/Logs")
    for f in cooked:
        if f.is_file():
            dst = stage / "Marvel" / "Content" / Path(rel + f.suffix)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
    return {"package": pkg, "ue_steps": rep["steps"], "ue_warnings": rep["warnings"], "slots": len(refs["materials"]),
            "refs": {k: v for k, v in refs.items() if k != "materials"},
            "staged": stage / "Marvel" / "Content" / Path(rel + ".uasset"), "vanilla_raw": raw / pkg}


def build(root: Path, game_arg=None) -> dict:
    """`mrforge mesh build`: the project build with every exported mesh cooked, edited or not (selftest round trip)."""
    from .build import run
    d = run(root, game_arg, force_meshes=True)
    d["packed"] = d["outputs"][1] if len(d["outputs"]) > 1 else None
    d["packages"] = [x["package"] for x in d["meshes"]] or d["packages"]
    return d


def verify_against_vanilla(root: Path, groot: Path, utoc: Path, pkg: str, vanilla_raw: Path, usmap: Path) -> dict:
    """Read the mesh back out of the packed mod with the game's mappings; slots, tags and bones must equal vanilla."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="mrf-mesh-"))
    try:
        extract_vanilla(layout(groot)["paks_dir"], tmp, [pattern_for(pkg)], mod=str(utoc))
        def info(p):
            t = T.run_tool("uassettool", ["skeletal_mesh_info", fwd(p), fwd(usmap)], timeout=600)
            text = t["stdout"] + t["stderr"]
            bones = re.search(r"Bone Count: (\d+)", text)
            return {"parsed": "Failed to parse" not in text, "bones": int(bones.group(1)) if bones else None,
                    "slots": [(x["slot"], x["tags"]) for x in parse_mesh_info(text)["materials"]]}
        v, b = info(vanilla_raw), info(tmp / pkg)
        problems = []
        if not b["parsed"]:
            problems.append("built mesh does not parse with the game's mappings")
        if b["bones"] != v["bones"]:
            problems.append(f"bones {b['bones']} != vanilla {v['bones']}")
        if [s for s, _ in b["slots"]] != [s for s, _ in v["slots"]]:
            problems.append("material slot names/order differ from vanilla")
        if b["slots"] != v["slots"]:
            problems.append("material slot gameplay tags differ from vanilla")
        return {"ok": not problems, "problems": problems, "bones": b["bones"], "slots": len(b["slots"])}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
