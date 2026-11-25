"""mrforge build: every changed asset of the project -> one mod container.

- textures: inject_texture into the vanilla package
- materials, physics: UAssetTool from_json on the edited JSON (physics read back at once, decision D25)
- meshes (changed .blend, or all with force_meshes): Unreal 5.3.2 import + cook (uebuild)
- sounds: the skin's Wwise banks with media replaced in place (snd.py, decision D31)
Packer: retoc when the stage holds legacy assets only; UAssetTool create_mod_iostore when it holds cooked meshes
(retoc refuses tagged cooks; UAssetTool packs both kinds, decision D26) or sound files (--hybrid: banks as loose
entries of the companion pak). A sound-only mod is a single .pak (UAssetTool create_pak), the shape community sound
mods ship (decision D32).

Only changed packages are staged. Output: dist/<PakName>_9999999_P.{pak,utoc,ucas} + dist/receipt.json.
Never obfuscated, stripped or encrypted (decision D8).
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from . import mat as M
from . import phys as PH
from . import project as P
from . import snd as SN
from . import tex as X
from . import tools as T
from .extract import load_lock
from .sync import require_usmap
from .tools import run_tool
from .util import ForgeError, fwd, iter_files, load_json, save_json, sha256_file

SUFFIX = "_9999999_P"
TRIPLE = (".pak", ".utoc", ".ucas")


def triple(root: Path, m: dict) -> dict[str, Path]:
    return {ext: Path(root) / "dist" / f"{m['pak_name']}{SUFFIX}{ext}" for ext in TRIPLE}


def built_files(root: Path, m: dict) -> dict[str, Path]:
    """The files the last build made: the IoStore triple, or the .pak alone for a sound-only mod (receipt container)."""
    tr = triple(root, m)
    rc = load_json(Path(root) / "dist" / "receipt.json", {})
    return {".pak": tr[".pak"]} if rc.get("container") == "pak" else tr


def _changed_materials(root: Path, lk: dict) -> list[str]:
    ops = M.load_ops(root)["materials"]
    out = set(k for k, v in ops.items() if v and k in lk["materials"])
    for k, rec in lk["materials"].items():
        w = Path(root) / rec["work_json"]
        if w.is_file() and sha256_file(w) != rec["json_sha256"]:
            out.add(k)
    return sorted(out)


def _changed_physics(root: Path, lk: dict) -> list[str]:
    ops = PH.load_ops(root)["assets"]
    out = set(k for k, v in ops.items() if v and k in lk["physics"])
    for k, rec in lk["physics"].items():
        w = Path(root) / rec["work_json"]
        if w.is_file() and sha256_file(w) != rec["json_sha256"]:
            out.add(k)
    return sorted(out)


def mesh_packages(root: Path, force: bool = False) -> list[str]:
    """Exported meshes whose .blend changed since import (all of them with force)."""
    exp = load_json(Path(root) / "work" / "mesh" / "export.json", {})
    out = []
    for x in exp.get("meshes", []):
        stem = Path(x["package"]).stem
        blend = Path(root) / "work" / "mesh" / f"{stem}.blend"
        if not blend.is_file():
            continue
        van = load_json(Path(root) / "work" / "mesh" / f"{stem}.vanilla.json", {})
        if force or not van.get("blend_sha256") or sha256_file(blend) != van["blend_sha256"]:
            out.append(x["package"])
    return out


def _readback_physics(staged: Path, usmap: Path, ops: list[dict]) -> list[str]:
    tmp = Path(tempfile.mkdtemp(prefix="mrf-phys-"))
    try:
        r = run_tool("uassettool", ["to_json", fwd(staged), fwd(usmap), fwd(tmp)], timeout=600)
        j = tmp / (staged.stem + ".json")
        if r["rc"] != 0 or not j.is_file():
            return ["the built asset does not convert back to JSON"]
        return PH.verify(load_json(j), ops)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _readback_from_mod(root: Path, groot, utoc: Path, pkg: str, usmap: Path, check) -> list[str]:
    from .game import layout
    from .uat import extract_vanilla, pattern_for
    tmp = Path(tempfile.mkdtemp(prefix="mrf-post-"))
    try:
        extract_vanilla(layout(groot)["paks_dir"], tmp / "raw", [pattern_for(pkg)], mod=str(utoc))
        r = run_tool("uassettool", ["to_json", fwd(tmp / "raw" / pkg), fwd(usmap), fwd(tmp / "json")], timeout=600)
        j = tmp / "json" / (Path(pkg).stem + ".json")
        if r["rc"] != 0 or not j.is_file():
            return ["not readable from the built mod"]
        return check(load_json(j))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(root: Path, game_arg=None, force_meshes: bool = False) -> dict:
    root = Path(root).resolve()  # UnrealEditor runs with its own working directory
    m = P.manifest(root)
    lk = load_lock(root, required=False)
    meshes = mesh_packages(root, force_meshes)
    snd_state = SN.load_state(root, required=False)
    snd_changed = SN.changed(root) if snd_state.get("banks") else []
    if not lk.get("changelist") and not meshes and not snd_state.get("banks"):
        raise ForgeError("NOT_EXTRACTED", "this project has no vanilla extraction yet",
                         "mrforge extract --textures <glob> | --materials | --physics | --sounds | --all, or mrforge mesh export")
    t0 = time.time()
    regenerated = X.regenerate_all(root, lk) if lk.get("textures") else []
    tex_changed = X.changed(root, lk) if lk.get("textures") else []
    mat_changed = _changed_materials(root, lk)
    phys_changed = _changed_physics(root, lk)
    if not (tex_changed or mat_changed or phys_changed or meshes or snd_changed):
        raise ForgeError("NOTHING_TO_BUILD", "no texture, material, physics asset, mesh or sound differs from vanilla",
                         "edit something first: mrforge tex ... / mat set ... / phys add-chain ... / sound replace ... / edit a .blend")
    all_ops = PH.load_ops(root)["assets"]
    phys_ue = [k for k in phys_changed if PH.editor_ops(all_ops.get(k, []))]
    phys_json = [k for k in phys_changed if k not in phys_ue]
    groot = cl = None
    if meshes or phys_ue or not lk.get("changelist"):
        from .game import find_game, version
        groot, _ = find_game(game_arg)
        cl = version(groot)["changelist"]
    changelist = lk.get("changelist") or snd_state.get("changelist") or cl
    usmap = require_usmap(changelist)
    stage_root = root / "build" / "stage"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage = stage_root / m["pak_name"]
    stage.mkdir(parents=True)
    staged, warnings, inputs, routes = [], [], {}, []
    for name in tex_changed:
        t = lk["textures"][name]
        van = root / "vanilla" / "raw" / t["package"]
        out = stage / t["package"]
        out.parent.mkdir(parents=True, exist_ok=True)
        png = root / t["work_png"]
        r = run_tool("uassettool", ["inject_texture", fwd(van), fwd(png), fwd(out), "--usmap", fwd(usmap)], timeout=900)
        if r["rc"] != 0 or not out.is_file():
            raise ForgeError("INJECT_FAILED", f"{name}: {(r['stdout'] + r['stderr']).strip()[-400:]}",
                             "check the PNG opens and is RGBA/RGB; rerun mrforge extract if vanilla files are missing")
        staged.append(t["package"])
        inputs[t["work_png"]] = sha256_file(png)
        if t.get("other_skin"):
            warnings.append(f"{name} lives under another skin id: every skin that uses it changes")
    if tex_changed:
        routes.append("texture")
    mjson = root / "build" / "materials"
    for key in mat_changed:
        rec = lk["materials"][key]
        d = M.apply(root, lk, key)
        jp = mjson / (key.replace("/", "__") + ".json")
        save_json(jp, d)
        out = stage / rec["package"]
        out.parent.mkdir(parents=True, exist_ok=True)
        r = run_tool("uassettool", ["from_json", fwd(jp), fwd(out), fwd(usmap)], timeout=600)
        if r["rc"] != 0 or not out.is_file():
            raise ForgeError("FROM_JSON_FAILED", f"{key}: {(r['stdout'] + r['stderr']).strip()[-400:]}",
                             "mrforge mat list to check values; reset with mrforge mat reset")
        staged.append(rec["package"])
        inputs[P.rel_project(root, jp)] = sha256_file(jp)
        if rec.get("other_skin"):
            warnings.append(f"{key} lives under another skin id: every skin that uses it changes")
    if mat_changed:
        routes.append("material")
    pjson = root / "build" / "physics"
    phys_checks = {}
    for key in phys_json:
        rec = lk["physics"][key]
        d = PH.apply(root, lk, key)
        jp = pjson / f"{key}.json"
        save_json(jp, d)
        out = stage / rec["package"]
        out.parent.mkdir(parents=True, exist_ok=True)
        r = run_tool("uassettool", ["from_json", fwd(jp), fwd(out), fwd(usmap)], timeout=600)
        if r["rc"] != 0 or not out.is_file():
            raise ForgeError("FROM_JSON_FAILED", f"{key}: {(r['stdout'] + r['stderr']).strip()[-400:]}",
                             "mrforge phys list to check the edits; reset with mrforge phys reset")
        probs = _readback_physics(out, usmap, all_ops.get(key, []))
        if probs:
            raise ForgeError("PHYS_READBACK_FAILED", f"{key}: {'; '.join(probs[:6])}",
                             "the edit did not survive serialization; mrforge phys reset and retry with other values")
        phys_checks[key] = {"ok": True, "ops": len(all_ops.get(key, []))}
        staged.append(rec["package"])
        inputs[P.rel_project(root, jp)] = sha256_file(jp)
    if phys_changed:
        routes.append("physics")
    mesh_done = []
    if meshes:
        from .uebuild import _cook_one
        mesh_done = [_cook_one(root, groot, pkg, usmap, stage) for pkg in meshes]
        staged += meshes
        routes.append("mesh")
        for pkg in meshes:
            b = root / "work" / "mesh" / (Path(pkg).stem + ".blend")
            inputs[P.rel_project(root, b)] = sha256_file(b)
    post_done = []
    if phys_ue:
        from .uepost import build_postprocess
        for key in phys_ue:
            rec = lk["physics"][key]
            post_done.append(build_postprocess(root, groot, key, rec, all_ops[key], usmap, stage, game_arg))
            staged.append(rec["package"])
        if "physics" not in routes:
            routes.append("physics")
    snd_done = {}
    if snd_changed:
        snd_done = SN.stage(root, stage)
        routes.append("sound")
        for rel in snd_done:
            for v in SN.load_ops(root)["replace"][rel].values():
                if v.get("file"):
                    inputs[v["file"]] = v["sha256"]
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    tr = triple(root, m)
    for f in tr.values():
        f.unlink(missing_ok=True)
    pak_only = bool(snd_done) and not staged
    if pak_only:
        packer = "uassettool"
        r = run_tool("uassettool", ["create_pak", fwd(tr[".pak"]), fwd(stage)], timeout=1800)
        ok = r["rc"] == 0 and tr[".pak"].is_file()
        tr = {".pak": tr[".pak"]}
    elif snd_done:
        packer = "uassettool"
        r = run_tool("uassettool", ["create_mod_iostore", fwd(dist / f"{m['pak_name']}{SUFFIX}"), fwd(stage), "--hybrid"],
                     timeout=1800)
        ok = r["rc"] == 0 and "SUCCESS" in r["stdout"]
    elif mesh_done or post_done:
        packer = "uassettool"
        uassets = sorted(f for f in iter_files(stage) if f.suffix == ".uasset")
        r = run_tool("uassettool", ["create_mod_iostore", fwd(dist / f"{m['pak_name']}{SUFFIX}"), *[fwd(f) for f in uassets]],
                     timeout=1800)
        ok = r["rc"] == 0 and "SUCCESS" in r["stdout"]
    else:
        packer = "retoc-rivals-cli"
        r = run_tool("retoc-rivals-cli", ["pack", fwd(stage), "--output", fwd(dist)], timeout=1800)
        ok = r["rc"] == 0
    missing = [str(p.name) for p in tr.values() if not p.is_file()]
    if not ok or missing:
        raise ForgeError("PACK_FAILED", f"{packer}: {(r['stdout'] + r['stderr']).strip()[-500:]} missing={missing}",
                         "run mrforge doctor; inspect build/stage")
    snd_checks = {}
    if snd_done:
        # The banks read back out of the built pak: HIRC and untouched media equal the game's, replaced media equal ours.
        probs = SN.verify_pak(root, tr[".pak"])
        if probs:
            raise ForgeError("SOUND_READBACK_FAILED", "; ".join(probs[:6]), "inspect build/stage/<mod>/Marvel/Content/WwiseAudio")
        snd_checks = {rel: {"ok": True, "replaced": len(v["replaced"]), "silenced": len(v["silenced"]),
                            "streamed": len(v["streamed"])} for rel, v in snd_done.items()}
    for x in post_done:
        # The cooked blueprint read back out of the built mod with the game's mappings: springs present and wired.
        probs = _readback_from_mod(root, groot, tr[".utoc"], lk["physics"][x["asset"]]["package"], usmap,
                                   lambda d, k=x["asset"]: PH.verify_springs(d, all_ops[k]))
        if probs:
            raise ForgeError("PHYS_READBACK_FAILED", f"{x['asset']}: {'; '.join(probs[:6])}",
                             "see build/postprocess/<asset>/ue_report.json")
        phys_checks[x["asset"]] = {"ok": True, "route": "editor", "springs": x["springs"],
                                   "vanilla_nodes": x["vanilla_nodes"], "note": x["behaviour_note"]}
    mesh_checks = {}
    if mesh_done:
        from .uebuild import verify_against_vanilla
        mesh_checks = {x["package"]: verify_against_vanilla(root, groot, tr[".utoc"], x["package"], x["vanilla_raw"], usmap)
                       for x in mesh_done}
        # Bind pose read back from the built mod: names/slots/weights can match while a bone transform does not.
        from .mesh import bind_check
        for pkg, probs in bind_check(root, tr[".utoc"], meshes, game_arg).items():
            c = mesh_checks.setdefault(pkg, {"ok": True, "problems": []})
            c["bind_pose"] = "equal to vanilla" if not probs else f"{len(probs)} bone transforms differ"
            if probs:
                c["problems"] = c["problems"] + [f"bind pose: {x}" for x in probs[:6]]
                c["ok"] = False
        if not any(p.endswith("_Lobby.uasset") for p in meshes):
            warnings.append("lobby mesh not in this build: hero select shows the vanilla (or another mod's) model")
    tool_names = ["uassettool", "retoc-rivals-cli"] + (["rivals-mesh-material-manager"] if mesh_done else [])
    tool_info = {n: {"tag": T.entry(n)["tag"], "exe_sha256": T.entry(n)["exe_sha256"]} for n in tool_names}
    receipt = {"mod": m["id"], "name": m["name"], "version": m["version"], "skin_id": m["skin_id"],
               "changelist": changelist, "usmap": usmap.name, "usmap_sha256": sha256_file(usmap),
               "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "tools": tool_info, "routes": routes, "packer": packer,
               "staged_packages": sorted(staged), "inputs": inputs,
               "physics_edits": sorted(lk["physics"][k]["package"] for k in phys_changed),
               "outputs": {p.name: sha256_file(p) for p in tr.values()},
               "pack_argv": r["argv"][1:], "options": {"obfuscate": False, "strip": False, "encrypt": False},
               "container": "pak" if pak_only else "iostore"}
    if packer == "uassettool":
        # UAssetTool writes every legacy .pak index with the game's own public AES key, as the game's paks are
        # (readable by FModel and every extraction tool); the IoStore container itself stays unencrypted (D8, D32).
        receipt["pak_index"] = "game AES key (public)"
    if snd_done:
        receipt["sound_banks"] = snd_done
    if mesh_done:
        from .ue import detect
        receipt.update(route="mesh", ue=detect().get("version"), mesh_packages=meshes, mesh_checks=mesh_checks)
    save_json(dist / "receipt.json", receipt)
    meshes_out = [{k: (str(v) if isinstance(v, Path) else v) for k, v in x.items() if k not in ("staged", "vanilla_raw")}
                  for x in mesh_done]
    return {"packages": len(staged), "routes": routes, "packer": packer, "sounds": snd_checks,
            "container": "pak" if pak_only else "iostore", "textures": tex_changed,
            "materials": mat_changed, "physics": phys_changed, "physics_checks": phys_checks, "meshes": meshes_out,
            "mesh_checks": mesh_checks, "regenerated": len(regenerated),
            "outputs": [str(p) for p in tr.values()], "seconds": round(time.time() - t0, 1), "warnings": warnings,
            "stage_files": sum(1 for _ in iter_files(stage))}
