"""mrforge extract: vanilla packages of the project's skin -> vanilla/ (legacy assets), PNG, JSON, lock.

Vanilla always comes from extract_iostore_legacy without --mod (decision D5), so a deployed mod can never
become the base of a new mod.
"""
from __future__ import annotations

import fnmatch
import shutil
import time
from pathlib import Path

from . import index as I
from . import project as P
from .game import find_game, layout, version
from .sync import require_usmap
from .uat import extract_vanilla, parse_batch_textures, pattern_for
from .tools import run_tool
from .util import ForgeError, fwd, iter_files, load_json, save_json, sha256_file


def lock_path(root: Path) -> Path:
    return Path(root) / "vanilla.lock.json"


def load_lock(root: Path, required: bool = True) -> dict:
    lk = load_json(lock_path(root), {})
    if required and not lk:
        raise ForgeError("NOT_EXTRACTED", "this project has no vanilla extraction yet",
                         "mrforge extract --textures <glob> | --materials | --all")
    lk.setdefault("textures", {})
    lk.setdefault("materials", {})
    lk.setdefault("physics", {})
    lk.setdefault("packages", {})
    return lk


def is_postprocess(path: str, skin_id: str) -> bool:
    """Post_<skin>_Physics / Post_<skin>_Lobby_Physics: the skin's post-process AnimBlueprints (physics route)."""
    stem = Path(path).stem
    return stem in (f"Post_{skin_id}_Physics", f"Post_{skin_id}_Lobby_Physics")


def select(idx: dict, skin_id: str, textures: list[str] | None, materials: bool, all_: bool,
           extra: list[str] | None, vfx: bool, physics: bool = False) -> list[dict]:
    pk = I.skin_packages(idx, skin_id)
    chosen = []
    for p in pk:
        cls = I.classify(p["path"])
        stem = Path(p["path"]).stem
        low = p["path"].lower()
        is_vfx = "/vfx/" in low
        if is_vfx and not vfx:
            continue
        if physics and is_postprocess(p["path"], skin_id):
            chosen.append(p)
        elif "/textures/" in low and stem.startswith("T_"):
            if all_ or (textures and any(fnmatch.fnmatchcase(stem, g) for g in textures)):
                chosen.append(p)
        elif cls == "material" and "/materials/" in low:
            if all_ or materials:
                chosen.append(p)
    for e in extra or []:
        n = I.norm_pkg(e)
        if not I.exists(idx, n):
            raise ForgeError("PACKAGE_NOT_IN_BUILD", f"{n} is not a vanilla package of this build", "mrforge skin inspect <id>")
        real = idx["_lower"][n.lower()]
        if all(c["path"] != real for c in chosen):
            chosen.append({"path": real})
    return chosen


def run(root: Path, textures: list[str] | None = None, materials: bool = False, all_: bool = False,
        extra: list[str] | None = None, vfx: bool = False, game_arg=None, physics: bool = False) -> dict:
    m = P.manifest(root)
    groot, _ = find_game(game_arg)
    lay = layout(groot)
    cl = version(groot)["changelist"]
    if m.get("game_changelist") and m["game_changelist"] != cl:
        raise ForgeError("PROJECT_BUILD_STALE", f"project was created for build {m['game_changelist']}, game is {cl}",
                         "re-extract in a fresh project, or update game_changelist in mrforge.json after reviewing")
    usmap = require_usmap(cl)
    idx = I.load(cl)
    chosen = select(idx, m["skin_id"], textures, materials, all_, extra, vfx, physics)
    if not chosen:
        raise ForgeError("NOTHING_SELECTED", "no package matched the selection",
                         "mrforge skin inspect <id> shows names; e.g. --textures \"T_*_Body_*\" or --materials")
    vroot = Path(root) / "vanilla"
    raw = vroot / "raw"
    t0 = time.time()
    res = extract_vanilla(lay["paks_dir"], raw, [pattern_for(c["path"]) for c in chosen])
    lk = load_lock(root, required=False)
    lk.update({"changelist": cl, "usmap": usmap.name, "usmap_sha256": sha256_file(usmap),
               "extracted": time.strftime("%Y-%m-%dT%H:%M:%S")})
    wanted = {c["path"].lower() for c in chosen}
    for c in chosen:
        base = raw / c["path"]
        stem = base.with_suffix("")
        files = {}
        for ext in (".uasset", ".uexp", ".ubulk", ".uptnl"):
            f = stem.with_suffix(ext)
            if f.is_file():
                files[ext] = sha256_file(f)
        if ".uasset" not in files:
            raise ForgeError("EXTRACT_INCOMPLETE", f"{c['path']} was not written by the extractor", "rerun mrforge extract")
        lk["packages"][c["path"]] = {"files": files}
    warnings = []
    other_skin = lambda p: f"/{m['skin_id']}/" not in p  # noqa: E731
    tex = [c["path"] for c in chosen if Path(c["path"]).stem.startswith("T_")]
    if tex:
        tmp_in = vroot / "_batch_in"
        if tmp_in.exists():
            shutil.rmtree(tmp_in)
        for tp in tex:
            for f in (raw / tp).parent.glob(Path(tp).stem + ".*"):
                dst = tmp_in / Path(tp).parent / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
        png_root = vroot / "png"
        r = run_tool("uassettool", ["batch_extract_texture", fwd(tmp_in), fwd(png_root), "--usmap", fwd(usmap)], timeout=1800)
        shutil.rmtree(tmp_in, ignore_errors=True)
        infos = {Path(i["rel"]).stem: i for i in parse_batch_textures(r["stdout"] + r["stderr"])}
        for tp in tex:
            name = Path(tp).stem
            info = infos.get(name)
            png = png_root / Path(tp).with_suffix(".png")
            if not info or not info.get("ok") or not png.is_file():
                warnings.append(f"{name}: texture decode failed ({(info or {}).get('error', 'no output')})")
                continue
            work = Path(root) / "work" / "textures" / f"{name}.png"
            if name in lk["textures"] and work.is_file() and sha256_file(work) != lk["textures"][name]["png_sha256"]:
                warnings.append(f"{name}: kept your edited work PNG")
            else:
                shutil.copyfile(png, work)
            lk["textures"][name] = {"package": tp, "width": info.get("width"), "height": info.get("height"),
                                    "format": info.get("format"), "mips": info.get("mips"),
                                    "vanilla_png": P.rel_project(root, png), "work_png": P.rel_project(root, work),
                                    "png_sha256": sha256_file(png), "other_skin": other_skin(tp)}
    mats = [c["path"] for c in chosen if I.classify(c["path"]) == "material"]
    if mats:
        jroot = vroot / "json"
        jroot.mkdir(parents=True, exist_ok=True)
        for mp in mats:
            src = raw / mp
            outdir = jroot / Path(mp).parent
            outdir.mkdir(parents=True, exist_ok=True)
            r = run_tool("uassettool", ["to_json", fwd(src), fwd(usmap), fwd(outdir)], timeout=600)
            j = outdir / (Path(mp).stem + ".json")
            if r["rc"] != 0 or not j.is_file():
                warnings.append(f"{Path(mp).stem}: to_json failed: {(r['stdout'] + r['stderr']).strip()[-200:]}")
                continue
            key = _mat_key(mp, m["skin_id"])
            work = Path(root) / "work" / "materials" / (key.replace("/", "__") + ".json")
            if key in lk["materials"] and work.is_file() and sha256_file(work) != lk["materials"][key]["json_sha256"]:
                warnings.append(f"{key}: kept your edited work JSON")
            else:
                shutil.copyfile(j, work)
            lk["materials"][key] = {"package": mp, "vanilla_json": P.rel_project(root, j),
                                    "work_json": P.rel_project(root, work), "json_sha256": sha256_file(j),
                                    "other_skin": other_skin(mp)}
    phys = [c["path"] for c in chosen if is_postprocess(c["path"], m["skin_id"])]
    if phys:
        from . import phys as PH
        jroot = vroot / "json"
        for pp in phys:
            outdir = jroot / Path(pp).parent
            outdir.mkdir(parents=True, exist_ok=True)
            r = run_tool("uassettool", ["to_json", fwd(raw / pp), fwd(usmap), fwd(outdir)], timeout=600)
            j = outdir / (Path(pp).stem + ".json")
            if r["rc"] != 0 or not j.is_file():
                warnings.append(f"{Path(pp).stem}: to_json failed: {(r['stdout'] + r['stderr']).strip()[-200:]}")
                continue
            key = Path(pp).stem
            work = Path(root) / "work" / "physics" / f"{key}.json"
            work.parent.mkdir(parents=True, exist_ok=True)
            if key in lk["physics"] and work.is_file() and sha256_file(work) != lk["physics"][key]["json_sha256"]:
                warnings.append(f"{key}: kept your edited work JSON")
            else:
                shutil.copyfile(j, work)
            try:
                info = PH.listing(load_json(j))
            except ForgeError as e:
                warnings.append(f"{key}: {e.message}")
                info = {"kawaii_nodes": 0, "chains": [], "anim_nodes": 0}
            if not info["kawaii_nodes"]:
                warnings.append(f"{key}: no KawaiiPhysics node (chains cannot be added here; lobby assets often have none)")
            lk["physics"][key] = {"package": pp, "vanilla_json": P.rel_project(root, j), "work_json": P.rel_project(root, work),
                                  "json_sha256": sha256_file(j), "kawaii_nodes": info["kawaii_nodes"],
                                  "chains": len(info["chains"]), "anim_nodes": info["anim_nodes"]}
    save_json(lock_path(root), lk)
    if m.get("game_changelist") is None:
        m["game_changelist"] = cl
        P.save_manifest(root, m)
    return {"selected": len(chosen), "converted": res["converted"], "textures": len(tex), "materials": len(mats),
            "physics": len(phys),
            "seconds": round(time.time() - t0, 1), "warnings": warnings, "lock": str(lock_path(root)),
            "unrequested_files": sorted(P.rel_project(root, f) for f in iter_files(raw)
                                        if f.suffix == ".uasset" and P.rel_project(root, f)[len("vanilla/raw/"):].lower()
                                        not in wanted | {k.lower() for k in lk["packages"]})[:20]}


def _mat_key(pkg: str, skin_id: str) -> str:
    """Material key relative to the skin folder: Materials/MI_x or Materials/Lobby/MI_x (names repeat in Lobby/)."""
    p = pkg[:-len(".uasset")] if pkg.endswith(".uasset") else pkg
    marker = f"/{skin_id}/"
    i = p.find(marker)
    return p[i + len(marker):] if i >= 0 else p.split("/Content/", 1)[-1]
