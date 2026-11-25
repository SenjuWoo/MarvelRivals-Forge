"""Physics route, editor-built: spring-bone jiggle in a skin's post-process AnimBlueprint (decision D29).

Used for assets the JSON route cannot extend, above all `Post_<skin>_Lobby_Physics` (hero select), which has no
KawaiiPhysics node. Unreal Engine 5.3.2 rebuilds the vanilla graph from its FModel JSON (KawaiiPhysicsRivals
importer), MrforgeAnimTools (a small editor plugin built here with the VS 2022 toolchain) wires the graph ends and
appends AnimNode_SpringBone nodes before the output, the blueprint is cooked at its vanilla path and packed alone:
the skeleton, scratch mesh and the importer's stub assets never leave the cook project.

Verified 2026-11-25 on Post_1061303_Lobby_Physics: 32 vanilla nodes and 30 links rebuilt, no skipped node types,
6 springs appended, compiled, cooked; read back with the game's mappings the CDO parses (45 anim nodes) and the
springs feed the output. One behaviour change: the vanilla graph's BlendListByInt index was driven by a curve in an
exposed-input function the importer does not rebuild, so it stays on branch 0 (the PoseDriver correctives).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import tools as T
from .home import home
from .ue import detect
from .util import EnvError, ForgeError, PKG_DIR, iter_files, load_json, run, save_json

PLUGIN = "MrforgeAnimTools"
# UBT 5.3.2's tested MSVC ranges in its own order of preference, then 14.38 (what the KawaiiPhysicsRivals README
# recommends). Newer toolsets (14.4x, 14.5x) break UE 5.3 headers.
PREFERRED_MSVC = ("14.36", "14.35", "14.34", "14.38", "14.37")
# vswhere ships with the Visual Studio Installer under %ProgramFiles(x86)%.
VSWHERE = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"


def msvc_toolsets() -> list[str]:
    """MSVC toolset folder versions of every Visual Studio 2022 instance."""
    if not VSWHERE.is_file():
        return []
    try:
        out = subprocess.run([str(VSWHERE), "-all", "-products", "*", "-version", "[17.0,18.0)", "-property",
                              "installationPath"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        msvc = Path(line.strip()) / "VC" / "Tools" / "MSVC"
        if msvc.is_dir():
            found += [p.name for p in msvc.iterdir() if p.is_dir()]
    return sorted(set(found))


def pick_compiler(versions: list[str]) -> str | None:
    for pref in PREFERRED_MSVC:
        hits = sorted((v for v in versions if v == pref or v.startswith(pref + ".")),
                      key=lambda v: [int(x) for x in v.split(".")])
        if hits:
            return hits[-1]
    return None


def _source_stamp(compiler: str) -> str:
    h = hashlib.sha256(compiler.encode())
    src = PKG_DIR / "unreal" / PLUGIN
    for f in sorted(iter_files(src)):
        h.update(str(f.relative_to(src)).encode())
        h.update(f.read_bytes())
    h.update(T.entry("kawaii-physics-rivals")["exe_sha256"].encode())
    return h.hexdigest()


def ensure_anim_tools() -> dict:
    """Copy KawaiiPhysicsRivals + MrforgeAnimTools into the cook project and build them once per source/compiler."""
    from .uebuild import init_project, project_dir
    ue = detect()
    if not ue["found"]:
        raise EnvError("UE_532_MISSING", "Unreal Engine 5.3.2 not found", "install it, or mrforge setup --ue <folder>")
    compiler = pick_compiler(msvc_toolsets())
    if not compiler:
        raise EnvError("MSVC_V143_MISSING", "no Visual Studio 2022 MSVC toolset UE 5.3 accepts (14.34-14.38)",
                       "install Visual Studio 2022 Build Tools with the C++ workload and the "
                       "'MSVC v143 - VS 2022 C++ x64/x86 build tools (v14.36)' component")
    d = project_dir()
    plugins = d / "Plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    stamp_file = plugins / ".mrforge-anim-stamp"
    stamp = _source_stamp(compiler)
    dll = plugins / PLUGIN / "Binaries" / "Win64" / f"UnrealEditor-{PLUGIN}.dll"
    if dll.is_file() and stamp_file.is_file() and stamp_file.read_text(encoding="utf-8").strip() == stamp:
        init_project(anim=True)
        return {"built": False, "compiler": compiler}
    for name, src in ((PLUGIN, PKG_DIR / "unreal" / PLUGIN),
                      ("KawaiiPhysics", T.tool_dir(T.require("kawaii-physics-rivals")) / "KawaiiPhysics")):
        if (plugins / name).exists():
            shutil.rmtree(plugins / name)
        shutil.copytree(src, plugins / name)
    init_project(anim=True)
    t0 = time.time()
    bat = Path(ue["root"]) / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    r = run([str(bat), "UnrealEditor", "Win64", "Development", f"-Project={d / 'Marvel.uproject'}", "-WaitMutex",
             f"-CompilerVersion={compiler}"], timeout=3600)
    if r["rc"] != 0 or not dll.is_file():
        errs = [ln for ln in r["stdout"].splitlines() if "error" in ln.lower()][-12:]
        raise ForgeError("ANIM_TOOLS_BUILD_FAILED", " | ".join(errs) or r["stdout"][-800:],
                         "see the Build.bat output; the plugin source is src/mrforge/unreal/MrforgeAnimTools")
    stamp_file.write_text(stamp, encoding="utf-8")
    return {"built": True, "compiler": compiler, "seconds": round(time.time() - t0, 1)}


def mesh_for(asset_key: str, m: dict) -> str:
    """The skeletal mesh whose post-process blueprint the asset is (lobby asset -> lobby mesh)."""
    base = f"Marvel/Content/Marvel/Characters/{m['hero_id']}/{m['skin_id']}/Meshes/SK_{m['hero_id']}_{m['skin_id']}"
    return base + ("_Lobby.uasset" if asset_key.endswith("_Lobby_Physics") else ".uasset")


def build_postprocess(root: Path, groot: Path, key: str, rec: dict, ops: list[dict], usmap: Path, stage: Path,
                      game_arg=None) -> dict:
    """Build one post-process AnimBlueprint with springs; copies the cooked asset into stage."""
    from . import phys as PH
    from .mesh import export_from_mod, run_blender
    from .uat import extract_vanilla, pattern_for
    from .game import layout
    from .project import manifest
    from .uebuild import init_project, project_dir, run_ue, vanilla_refs
    m = manifest(root)
    tools_info = ensure_anim_tools()
    work = root / "build" / "postprocess" / key
    work.mkdir(parents=True, exist_ok=True)
    mesh_pkg = mesh_for(key, m)
    raw = root / "vanilla" / "raw"
    extract_vanilla(layout(groot)["paks_dir"], raw, [pattern_for(mesh_pkg)])
    refs = vanilla_refs(raw / mesh_pkg, usmap)
    asset_path = "/Game/" + rec["package"][len("Marvel/Content/"):-len(".uasset")]
    if refs.get("postprocess") != asset_path:
        raise ForgeError("POSTPROCESS_NOT_USED", f"{Path(mesh_pkg).stem} uses {refs.get('postprocess')}, not {asset_path}",
                         "springs only take effect in the post-process blueprint the mesh actually uses")
    if not refs.get("skeleton"):
        raise ForgeError("MESH_REFS_UNRESOLVED", f"no skeleton reference in {Path(mesh_pkg).stem}")
    # Vanilla graph (FModel JSON) and the mesh (for its skeleton), both from the game containers only.
    js = export_from_mod(None, [rec["package"]], work, game_arg, mode="properties", ext=".json")
    um = export_from_mod(None, [mesh_pkg], work, game_arg)
    if rec["package"] not in js or mesh_pkg not in um:
        raise ForgeError("POSTPROCESS_EXPORT_FAILED", f"vanilla export incomplete: json={list(js)} mesh={list(um)}")
    addon = T.tool_dir(T.require("ueformat-blender"))
    blend, fbx = work / "skeleton_source.blend", work / "skeleton_source.fbx"
    run_blender(["import", str(addon), str(um[mesh_pkg]), str(blend)])
    summ = run_blender(["fbx", str(blend), str(fbx)])
    spec = {"springs": [{"bone": b, **op.get("params", {})} for op in ops if op["op"] == "springs" for b in op["bones"]]}
    # A spring on a bone the skeleton lacks compiles fine and does nothing in game: refuse it here.
    bones = {b["name"] for a in summ.get("armatures", []) for b in a["bones"]}
    missing = [s["bone"] for s in spec["springs"] if s["bone"] not in bones]
    if missing:
        raise ForgeError("SPRING_BONE_UNKNOWN", f"not in {Path(mesh_pkg).stem}'s skeleton: {missing}",
                         "check the names in Blender (mrforge mesh blend) and mrforge phys reset + springs again")
    job = {"fbx": str(fbx.resolve()), "mesh_tmp_path": "/Game/MrforgeTmp/SK_SkeletonSource",
           "skeleton_path": refs["skeleton"], "abp_path": asset_path, "fmodel_json": str(js[rec["package"]].resolve()),
           "spec": spec}
    jp = work / "ue_job.json"
    save_json(jp, job)
    d = project_dir()
    for sub in ("Content/Marvel", "Content/MrforgeTmp", "Saved/Cooked"):
        shutil.rmtree(d / sub, ignore_errors=True)
    init_project(anim=True)
    r = run_ue(["-run=pythonscript", f"-script={PKG_DIR / 'unreal' / 'build_postprocess.py'}"],
               env={"MRFORGE_UE_JOB": str(jp.resolve())})
    rep = next((json.loads(ln.split("MRFORGE_JSON:", 1)[1]) for ln in r["stdout"].splitlines() if "MRFORGE_JSON:" in ln), None)
    save_json(work / "ue_report.json", rep or {"stdout_tail": r["stdout"][-4000:]})
    if not rep or not rep.get("ok"):
        raise ForgeError("POSTPROCESS_BUILD_FAILED", (rep or {}).get("error") or r["stdout"][-800:],
                         f"see {work / 'ue_report.json'} and .mrforge/ue/Marvel/Saved/Logs")
    c = run_ue(["-run=cook", "-targetplatform=Windows", "-iterate=false"], timeout=7200)
    rel = rec["package"][len("Marvel/Content/"):-len(".uasset")]
    cooked_root = d / "Saved" / "Cooked" / "Windows" / "Marvel" / "Content"
    files = [cooked_root / (rel + ext) for ext in (".uasset", ".uexp")]
    if not files[0].is_file():
        errs = [ln for ln in c["stdout"].splitlines() if "Error" in ln][-15:]
        raise ForgeError("UE_COOK_FAILED", " | ".join(errs) or c["stdout"][-800:], "see .mrforge/ue/Marvel/Saved/Logs")
    for f in files:
        if f.is_file():
            dst = stage / "Marvel" / "Content" / Path(rel + f.suffix)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dst)
    imp = rep.get("import", {})
    return {"asset": key, "staged": stage / "Marvel" / "Content" / Path(rel + ".uasset"), "springs": len(spec["springs"]),
            "vanilla_nodes": imp.get("nodes"), "vanilla_links": imp.get("links"), "stubs_not_packed": len(imp.get("stubs", [])),
            "tail": rep.get("finish", {}).get("tail"), "anim_tools": tools_info,
            "behaviour_note": "vanilla BlendListByInt stays on branch 0 (PoseDriver correctives always on)"}
