"""mrforge skin inspect: what a skin is made of in this build, what it shares, what overrides it."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import index as I
from . import mat as M
from .catalog import resolve_skin
from .game import find_game, layout, version
from .home import home
from .mods import package_owners, scan
from .sync import require_usmap
from .tools import run_tool
from .uat import extract_vanilla, parse_batch_textures, parse_mesh_info, pattern_for
from .util import fwd, load_json, save_json


def inspect(skin_text: str, quick: bool = False, game_arg=None, refresh: bool = False) -> dict:
    s = resolve_skin(skin_text)
    sid = s["skin_id"]
    groot, _ = find_game(game_arg)
    cl = version(groot)["changelist"]
    idx = I.load(cl)
    pk = I.skin_packages(idx, sid)
    if not pk:
        from .util import ForgeError
        raise ForgeError("SKIN_NOT_IN_BUILD", f"skin {sid} has no packages in build {cl}",
                         "check the id with mrforge skin find; new skins may need mrforge index after a patch")
    groups: dict[str, list[str]] = {}
    for p in pk:
        groups.setdefault(I.classify(p["path"]), []).append(p["path"])
    out = {"skin": s, "changelist": cl, "package_count": len(pk),
           "counts": {k: len(v) for k, v in sorted(groups.items())},
           "meshes": [Path(p).stem for p in groups.get("mesh", [])],
           "physics": [Path(p).stem for p in groups.get("physics", [])],
           "materials": [p.split(f"/{sid}/", 1)[-1][:-7] for p in groups.get("material", [])],
           "textures": [Path(p).stem for p in groups.get("texture", [])]}
    try:
        mods = scan(layout(groot)["mods_dir"])
        owners = package_owners(mods)
        out["overridden_by_mods"] = {p: owners[p.lower()] for p in (x["path"] for x in pk) if p.lower() in owners}
    except Exception as e:  # advisory; retoc may be missing
        out["overridden_by_mods"] = {"skipped": str(e)}
    if quick:
        return out
    out["deep"] = _deep(groot, cl, sid, groups, refresh)
    return out


def _deep(groot: Path, cl: int, sid: str, groups: dict, refresh: bool) -> dict:
    cache = home() / "cache" / "vanilla" / str(cl) / sid
    marker = cache / "inspect.json"
    if marker.is_file() and not refresh:
        return load_json(marker)
    usmap = require_usmap(cl)
    if cache.exists():
        shutil.rmtree(cache)
    raw = cache / "raw"
    meshes = [p for p in groups.get("mesh", []) if "/meshes/" in p.lower()]
    sel = meshes + groups.get("material", []) + [p for p in groups.get("texture", []) if "/vfx/" not in p.lower()]
    t0 = time.time()
    extract_vanilla(layout(groot)["paks_dir"], raw, [pattern_for(p) for p in sel])
    deep: dict = {"meshes": {}, "materials": {}, "textures": {}, "shared_from_other_skins": []}
    for mp in meshes:
        r = run_tool("uassettool", ["skeletal_mesh_info", fwd(raw / mp), fwd(usmap)], timeout=600)
        info = parse_mesh_info(r["stdout"])
        deep["meshes"][Path(mp).stem] = {"material_slots": info["material_count"],
                                         "slots": [{"i": x["index"], "slot": x["slot"], "tags": x["tags"]} for x in info["materials"]]}
    jd = cache / "json"
    shared = set()
    for mp in groups.get("material", []):
        sub = jd / Path(mp).parent.name
        sub.mkdir(parents=True, exist_ok=True)
        r = run_tool("uassettool", ["to_json", fwd(raw / mp), fwd(usmap), fwd(sub)], timeout=600)
        j = sub / (Path(mp).stem + ".json")
        if not j.is_file():
            continue
        d = load_json(j)
        key = mp.split(f"/{sid}/", 1)[-1][:-7]
        try:
            refs = M.package_refs(d)
            deep["materials"][key] = {"parent": M.parent(d), "params": len(M.params(d)),
                                      "textures": [r_ for r_ in refs if "/Textures/" in r_]}
            for r_ in refs:
                if f"/{sid}/" not in r_ and "/Characters/" in r_:
                    shared.add(r_)
        except Exception:
            deep["materials"][key] = {"error": "not a material instance"}
    deep["shared_from_other_skins"] = sorted(shared)
    r = run_tool("uassettool", ["batch_extract_texture", fwd(raw), fwd(cache / "mip"), "--usmap", fwd(usmap), "--mip", "8"],
                 timeout=1800)
    for t in parse_batch_textures(r["stdout"] + r["stderr"]):
        deep["textures"][Path(t["rel"]).stem] = {"size": f"{t.get('width')}x{t.get('height')}", "format": t.get("format"),
                                                 "mips": t.get("mips")}
    shutil.rmtree(cache / "mip", ignore_errors=True)
    shutil.rmtree(raw, ignore_errors=True)
    deep["seconds"] = round(time.time() - t0, 1)
    save_json(marker, deep)
    return deep
