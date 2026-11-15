"""Mesh route (v0.2): export (fmodel-mcp, vanilla view) -> Blender (.blend, FBX) -> check against vanilla.

The vanilla view: fmodel-mcp mounts every archive below the folder it opens, including ~mods, and has no
exclusion option. The forge therefore opens a temporary folder of hardlinks to the top-level game containers
(same volume, outside the game folder) and deletes it in `finally` (verified 2026-11-15: 154 links in 0.03 s,
76 archives mounted, the overridden mesh resolved to pakchunkCharacter).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from . import fmcp
from . import index as I
from . import project as P
from . import tools as T
from .game import find_game, layout, version
from .home import home
from .sync import aes_key, require_usmap
from .util import EnvError, ForgeError, PKG_DIR, load_json, run, save_json

VIEW_PREFIX = "mrforge-vanilla-view-"
GAME_PROFILE = "GAME_MarvelRivals"


def view_parent(game_root: Path) -> Path:
    """Same volume as the game, outside the game folder: the Steam library root when the layout is Steam's."""
    g = Path(game_root)
    if g.parent.name.lower() == "common" and g.parent.parent.name.lower() == "steamapps":
        return g.parent.parent.parent
    return g.parent


def leftover_views(game_root: Path) -> list[str]:
    par = view_parent(game_root)
    return sorted(str(p) for p in par.glob(VIEW_PREFIX + "*")) if par.is_dir() else []


@contextmanager
def vanilla_view(game_root: Path):
    paks = layout(game_root)["paks_dir"]
    view = view_parent(game_root) / f"{VIEW_PREFIX}{os.getpid()}"
    if view.exists():
        shutil.rmtree(view, ignore_errors=True)
    try:
        view.mkdir()
        for f in paks.iterdir():
            if f.is_file() and f.suffix.lower() in (".utoc", ".ucas", ".pak", ".sig"):
                os.link(f, view / f.name)
    except OSError as e:
        shutil.rmtree(view, ignore_errors=True)
        raise EnvError("VANILLA_VIEW_UNAVAILABLE", f"cannot hardlink the game containers into {view}: {e}",
                       "the folder must be on the game's drive and writable; or disable mods that override this skin and retry") from e
    try:
        yield view
    finally:
        shutil.rmtree(view, ignore_errors=True)


def mesh_paths(m: dict, lobby: bool) -> list[str]:
    base = f"Marvel/Content/Marvel/Characters/{m['hero_id']}/{m['skin_id']}/Meshes/SK_{m['hero_id']}_{m['skin_id']}"
    return [base + ".uasset"] + ([base + "_Lobby.uasset"] if lobby else [])


def export(root: Path, lobby: bool = False, game_arg=None) -> dict:
    root = Path(root)
    m = P.manifest(root)
    groot, _ = find_game(game_arg)
    cl = version(groot)["changelist"]
    idx = I.load(cl)
    targets = mesh_paths(m, lobby)
    missing = [t for t in targets if not I.exists(idx, t)]
    if missing:
        raise ForgeError("MESH_NOT_IN_BUILD", f"not in build {cl}: {missing}", "mrforge skin inspect <id> lists the meshes")
    usmap = require_usmap(cl)
    key = aes_key()
    if not key:
        raise EnvError("AES_KEY_MISSING", "no AES key stored", "run: mrforge sync")
    T.require("fmodel-mcp")
    oodle = T.tool_dir(T.entry("uassettool")) / "oo2core_9_win64.dll"
    out_root = home() / "cache" / "fmcp" / "out"
    dest = root / "work" / "mesh" / "vanilla"
    t0 = time.time()
    results = []
    with vanilla_view(groot) as view:
        cfg = fmcp.write_config(home() / "cache" / "fmcp" / "config.json", [view, usmap.parent], out_root,
                                oodle if oodle.is_file() else None)
        argv = T.argv_for("fmodel-mcp")
        with fmcp.McpClient(argv + ["--config", str(cfg)], cwd=str(Path(argv[-1]).parent)) as c:
            c.initialize()
            sid = c.call("fmodel_open_game", {"options": {"directory": str(view), "game": GAME_PROFILE,
                                                          "mappingsPath": str(usmap), "aesKeys": {"0" * 32: key}}},
                         timeout=600)["sessionId"]
            try:
                for t in targets:
                    hits = c.call("fmodel_search_assets", {"sessionId": sid, "query": Path(t).stem, "packagesOnly": True})
                    arch = [h.get("archive", "") for h in hits.get("items", []) if h["path"].lower() == t.lower()]
                    if not arch or not all(a.lower().startswith(("pakchunk", "global")) for a in arch):
                        raise ForgeError("VANILLA_VIEW_LEAK", f"{t} resolved to {arch}", "report this; the view should hold vanilla only")
                    job = c.call("fmodel_start_export", {"sessionId": sid, "request": {
                        "paths": [t], "mode": "converted", "meshFormat": "UEFormat", "textureFormat": "Png"}})
                    st = fmcp.wait_job(c, sid, job["jobId"])
                    if st["state"] != "completed":
                        raise ForgeError("MESH_EXPORT_FAILED", f"{t}: {st['state']} {st.get('error')}", "mrforge doctor")
                    r = c.call("fmodel_job_results", {"sessionId": sid, "jobId": job["jobId"]})
                    outdir = Path(st["outputDirectory"]) / "converted"
                    files = []
                    for item in r.get("results", {}).get("items", []):
                        for f in item.get("files", []):
                            fp = Path(f)
                            try:
                                rel = fp.relative_to(outdir)
                            except ValueError:
                                continue
                            target = dest / rel
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(fp, target)
                            files.append(rel.as_posix())
                    shutil.rmtree(Path(st["outputDirectory"]), ignore_errors=True)
                    results.append({"package": t, "archive": arch[0], "files": len(files),
                                    "uemodel": next((f for f in files if f.endswith(".uemodel")), None)})
            finally:
                try:
                    c.call("fmodel_close_game", {"sessionId": sid}, timeout=60)
                except ForgeError:
                    pass
    rec = {"changelist": cl, "exported": time.strftime("%Y-%m-%dT%H:%M:%S"), "meshes": results,
           "seconds": round(time.time() - t0, 1)}
    save_json(root / "work" / "mesh" / "export.json", rec)
    return rec


# --- Blender leg --------------------------------------------------------------

def blender_exe() -> str:
    exe = shutil.which("blender") or os.environ.get("MRFORGE_BLENDER")
    if not exe:
        raise EnvError("BLENDER_MISSING", "blender is not on PATH", "install Blender 4.2+ or set MRFORGE_BLENDER")
    return exe


def run_blender(args: list[str], timeout: float = 900) -> dict:
    script = PKG_DIR / "blender" / "mesh_tool.py"
    r = run([blender_exe(), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script), "--", *args],
            timeout=timeout)
    for line in r["stdout"].splitlines():
        if line.startswith("MRFORGE_JSON:"):
            return json.loads(line[len("MRFORGE_JSON:"):])
    raise ForgeError("BLENDER_FAILED", (r["stdout"] + r["stderr"]).strip()[-600:], "run the same command with Blender's GUI to see the error")


def _uemodels(root: Path) -> list[Path]:
    rec = load_json(Path(root) / "work" / "mesh" / "export.json", {})
    if not rec:
        raise ForgeError("MESH_NOT_EXPORTED", "no exported mesh in this project", "mrforge mesh export")
    return [Path(root) / "work" / "mesh" / "vanilla" / x["uemodel"] for x in rec["meshes"] if x.get("uemodel")]


def blend(root: Path, force: bool = False) -> dict:
    root = Path(root)
    addon = T.tool_dir(T.require("ueformat-blender"))
    out = []
    for um in _uemodels(root):
        b = root / "work" / "mesh" / (um.stem + ".blend")
        if b.exists() and not force:
            out.append({"blend": str(b), "skipped": "exists (use --force to re-import; your edits would be lost)"})
            continue
        res = run_blender(["import", str(addon), str(um), str(b)])
        save_json(root / "work" / "mesh" / (um.stem + ".vanilla.json"), {k: res[k] for k in ("meshes", "armatures")})
        out.append({"blend": str(b), "meshes": [{"name": x["name"], "vertices": x["vertices"],
                                                 "material_slots": len(x["material_slots"])} for x in res["meshes"]],
                    "bones": [a["bone_count"] for a in res["armatures"]]})
    return {"blends": out, "next": "edit the .blend in Blender (keep bone names and material slots), then mrforge mesh check"}


def fbx(root: Path) -> dict:
    root = Path(root)
    out = []
    for um in _uemodels(root):
        b = root / "work" / "mesh" / (um.stem + ".blend")
        if not b.is_file():
            raise ForgeError("NO_BLEND", f"{b.name} missing", "mrforge mesh blend")
        f = root / "build" / "fbx" / (um.stem + ".fbx")
        f.parent.mkdir(parents=True, exist_ok=True)
        res = run_blender(["fbx", str(b), str(f)])
        out.append({"fbx": str(f), "size": f.stat().st_size if f.is_file() else 0, "meshes": len(res["meshes"])})
    return {"fbx": out}


def compare(vanilla: dict, current: dict) -> list[str]:
    """Problems that break a cooked mesh's binding to the game's skeleton and materials."""
    problems = []
    va, ca = vanilla["armatures"], current["armatures"]
    if len(va) != len(ca):
        problems.append(f"armature count {len(ca)} != vanilla {len(va)}")
    for a, b in zip(va, ca):
        if a["hierarchy_sha256"] != b["hierarchy_sha256"]:
            vb = {x["name"]: x["parent"] for x in a["bones"]}
            cb = {x["name"]: x["parent"] for x in b["bones"]}
            miss = sorted(set(vb) - set(cb))[:8]
            extra = sorted(set(cb) - set(vb))[:8]
            moved = sorted(n for n in set(vb) & set(cb) if vb[n] != cb[n])[:8]
            problems.append(f"bones differ: missing {miss} extra {extra} reparented {moved}")
    vslots = [s for mm in vanilla["meshes"] for s in mm["material_slots"]]
    cslots = [s for mm in current["meshes"] for s in mm["material_slots"]]
    if vslots != cslots:
        problems.append(f"material slots differ (names and order must match vanilla): vanilla {vslots[:6]}... now {cslots[:6]}...")
    bones = {x["name"] for a in ca for x in a["bones"]}
    for mm in current["meshes"]:
        stray = [g for g in mm["vertex_groups"] if g not in bones]
        if stray:
            problems.append(f"{mm['name']}: vertex groups that are not bones: {stray[:8]}")
    return problems


def check(root: Path) -> tuple[dict, bool]:
    root = Path(root)
    out, ok = [], True
    for um in _uemodels(root):
        b = root / "work" / "mesh" / (um.stem + ".blend")
        van = load_json(root / "work" / "mesh" / (um.stem + ".vanilla.json"), {})
        if not b.is_file() or not van:
            raise ForgeError("NO_BLEND", f"{b.name} or its vanilla summary missing", "mrforge mesh blend")
        cur = run_blender(["summary", str(b)])
        probs = compare(van, cur)
        ok = ok and not probs
        out.append({"mesh": um.stem, "problems": probs,
                    "triangles": sum(x["triangles"] for x in cur["meshes"]),
                    "vanilla_triangles": sum(x["triangles"] for x in van["meshes"])})
    return {"checks": out}, ok
