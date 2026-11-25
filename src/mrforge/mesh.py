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
from .util import EnvError, ForgeError, PKG_DIR, UsageError, load_json, run, save_json, sha256_file

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
        # blend_sha256 marks the unedited import: mrforge build cooks only meshes whose .blend differs from it.
        save_json(root / "work" / "mesh" / (um.stem + ".vanilla.json"),
                  {**{k: res[k] for k in ("meshes", "armatures")}, "blend_sha256": sha256_file(b)})
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


def inflate(root: Path, bones: list[str], factor: float, which: str = "all", children: bool = True) -> dict:
    """Weight-driven body-shape edit on the project's .blend files (e.g. chest or hips bigger/smaller).

    Every edit is appended to work/mesh/edits.json; re-import with mesh blend --force to start over."""
    root = Path(root)
    if not bones:
        raise UsageError("name at least one bone", "--bone L_Breast_01_Jnt --bone R_Breast_01_Jnt")
    if not 0.2 <= factor <= 3.0:
        raise UsageError(f"factor {factor} is outside 0.2..3.0", "1.2 = 20% bigger, 0.9 = 10% smaller")
    out = []
    for um in _uemodels(root):
        lobby = um.stem.endswith("_Lobby")
        if which == "game" and lobby or which == "lobby" and not lobby:
            continue
        b = root / "work" / "mesh" / (um.stem + ".blend")
        if not b.is_file():
            raise ForgeError("NO_BLEND", f"{b.name} missing", "mrforge mesh blend")
        spec = root / "build" / "inflate.json"
        save_json(spec, {"bones": [{"bone": x, "factor": factor} for x in bones], "children": children})
        res = run_blender(["inflate", str(b), str(spec)])
        out.append({"blend": b.name, "result": res["inflate"]})
    if not out:
        raise ForgeError("NO_BLEND", f"no .blend matches --mesh {which}", "mrforge mesh blend")
    log = load_json(root / "work" / "mesh" / "edits.json", {"edits": []})
    log["edits"].append({"op": "inflate", "bones": bones, "factor": factor, "mesh": which, "children": children,
                         "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "result": out})
    save_json(root / "work" / "mesh" / "edits.json", log)
    return {"edited": out, "next": "mrforge mesh check, then mrforge build"}


def preview(root: Path, focus: str | None = None) -> dict:
    """build/preview/<mesh>.png: vanilla | edited, front and side, so an edit is looked at before the 2-minute cook."""
    from PIL import Image, ImageDraw
    root = Path(root)
    addon = T.tool_dir(T.require("ueformat-blender"))
    prev = root / "build" / "preview"
    prev.mkdir(parents=True, exist_ok=True)
    out = []
    for um in _uemodels(root):
        b = root / "work" / "mesh" / (um.stem + ".blend")
        if not b.is_file():
            raise ForgeError("NO_BLEND", f"{b.name} missing", "mrforge mesh blend")
        vb = prev / f"{um.stem}.vanilla.blend"
        if not vb.is_file():
            run_blender(["import", str(addon), str(um), str(vb)])
        for tag, src in (("vanilla", vb), ("edited", b)):
            run_blender(["render", str(src), str(prev / f"{um.stem}.{tag}")] + ([focus] if focus else []))
        tiles = [Image.open(prev / f"{um.stem}.{tag}_{v}.png").convert("RGB")
                 for v in ("front", "side") for tag in ("vanilla", "edited")]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * 4, h + 24), (30, 30, 30))
        dr = ImageDraw.Draw(sheet)
        for i, (im, label) in enumerate(zip(tiles, ("front vanilla", "front edited", "side vanilla", "side edited"))):
            sheet.paste(im, (i * w, 24))
            dr.text((i * w + 6, 6), f"{um.stem}  {label}", fill=(230, 230, 230))
        png = prev / f"{um.stem}.png"
        sheet.save(png)
        for f in prev.glob(f"{um.stem}.*_*.png"):
            f.unlink()
        out.append(str(png))
    return {"previews": out, "next": "open the PNGs and look at them, then mrforge build"}


def compare_bind(vanilla: list[dict], built: list[dict], pos_tol: float = 0.05, rot_tol: float = 1e-3,
                 scale_tol: float = 1e-3) -> list[str]:
    """Reference-skeleton transforms of a built mesh vs vanilla (local position cm, rotation quaternion, scale).

    Names, order and weights can all match while a transform differs; the game then deforms the mesh (a root bone
    scale of 100 shrank every vertex onto its bone). q and -q are the same rotation."""
    probs = []
    if [b["name"] for b in vanilla] != [b["name"] for b in built]:
        return [f"bone names/order differ ({len(built)} built vs {len(vanilla)} vanilla)"]
    for v, b in zip(vanilla, built):
        if max(abs(x - y) for x, y in zip(v["scale"], b["scale"])) > scale_tol:
            probs.append(f"{b['name']}: scale {[round(x, 4) for x in b['scale']]} != vanilla {[round(x, 4) for x in v['scale']]}")
        if max(abs(x - y) for x, y in zip(v["position"], b["position"])) > pos_tol:
            probs.append(f"{b['name']}: position {[round(x, 3) for x in b['position']]} != vanilla "
                         f"{[round(x, 3) for x in v['position']]}")
        dot = abs(sum(x * y for x, y in zip(v["rotation"], b["rotation"])))
        if 1.0 - dot > rot_tol:
            probs.append(f"{b['name']}: rotation differs from vanilla (|dot| {dot:.4f})")
    return probs


def raw_bones(uemodel: Path) -> list[dict]:
    addon = T.tool_dir(T.require("ueformat-blender"))
    return run_blender(["bones", str(addon), str(uemodel)])["bones"]


def export_from_mod(utoc: Path | None, packages: list[str], dest: Path, game_arg=None, mode: str = "converted",
                    ext: str = ".uemodel") -> dict:
    """Export packages as the game loads them: vanilla containers + this one mod (fmodel-mcp, temporary view).

    utoc=None exports vanilla only. mode "converted" gives .uemodel meshes; "properties" gives FModel JSON."""
    groot, _ = find_game(game_arg)
    usmap = require_usmap(version(groot)["changelist"])
    key = aes_key()
    if not key:
        raise EnvError("AES_KEY_MISSING", "no AES key stored", "run: mrforge sync")
    T.require("fmodel-mcp")
    oodle = T.tool_dir(T.entry("uassettool")) / "oo2core_9_win64.dll"
    out_root = home() / "cache" / "fmcp" / "out"
    dest.mkdir(parents=True, exist_ok=True)
    found = {}
    utoc = Path(utoc) if utoc else None
    with vanilla_view(groot) as view:
        if utoc:
            md = view / "~mods"
            md.mkdir()
            for f in utoc.parent.glob(utoc.stem + ".*"):
                if f.suffix.lower() in (".utoc", ".ucas", ".pak"):
                    shutil.copyfile(f, md / f.name)
        cfg = fmcp.write_config(home() / "cache" / "fmcp" / "readback.json", [view, usmap.parent], out_root,
                                oodle if oodle.is_file() else None)
        argv = T.argv_for("fmodel-mcp")
        with fmcp.McpClient(argv + ["--config", str(cfg)], cwd=str(Path(argv[-1]).parent)) as c:
            c.initialize()
            sid = c.call("fmodel_open_game", {"options": {"directory": str(view), "game": GAME_PROFILE,
                                                          "mappingsPath": str(usmap), "aesKeys": {"0" * 32: key}}},
                         timeout=600)["sessionId"]
            try:
                for pkg in packages:
                    hits = c.call("fmodel_search_assets", {"sessionId": sid, "query": Path(pkg).stem, "packagesOnly": True})
                    arch = [h.get("archive", "") for h in hits.get("items", []) if h["path"].lower() == pkg.lower()]
                    if utoc and not any(a.lower() == utoc.name.lower() for a in arch):
                        raise ForgeError("MESH_NOT_IN_MOD", f"{pkg} not found in {utoc.name} (archives {arch})")
                    if not utoc and not arch:
                        raise ForgeError("PACKAGE_NOT_IN_BUILD", f"{pkg} not found in the game containers")
                    req = {"paths": [pkg], "mode": mode}
                    if mode == "converted":
                        req.update(meshFormat="UEFormat", textureFormat="Png")
                    job = c.call("fmodel_start_export", {"sessionId": sid, "request": req})
                    st = fmcp.wait_job(c, sid, job["jobId"])
                    if st["state"] != "completed":
                        raise ForgeError("MESH_READBACK_FAILED", f"{pkg}: {st['state']} {st.get('error')}")
                    um = next(Path(st["outputDirectory"]).rglob(Path(pkg).stem + ext), None)
                    if um:
                        found[pkg] = dest / um.name
                        shutil.copyfile(um, found[pkg])
                    shutil.rmtree(Path(st["outputDirectory"]), ignore_errors=True)
            finally:
                try:
                    c.call("fmodel_close_game", {"sessionId": sid}, timeout=60)
                except ForgeError:
                    pass
    return found


def bind_check(root: Path, utoc: Path, packages: list[str], game_arg=None) -> dict:
    """package -> bind-pose problems of the mesh read back from the built mod (empty list = equal to vanilla)."""
    root = Path(root)
    exp = load_json(root / "work" / "mesh" / "export.json", {})
    vanilla = {x["package"]: root / "work" / "mesh" / "vanilla" / x["uemodel"] for x in exp.get("meshes", []) if x.get("uemodel")}
    built = export_from_mod(utoc, packages, root / "build" / "readback", game_arg)
    out = {}
    for pkg in packages:
        if pkg not in vanilla or not vanilla[pkg].is_file():
            out[pkg] = ["vanilla .uemodel missing (mrforge mesh export)"]
        elif pkg not in built:
            out[pkg] = ["mesh did not export from the built mod"]
        else:
            out[pkg] = compare_bind(raw_bones(vanilla[pkg]), raw_bones(built[pkg]))
            out[pkg] += normals_problem(normal_stats(vanilla[pkg], built[pkg]))
    return out


NORMALS_P95_MAX = 5.0  # degrees; a faithful cook measured 0.6 (quantization), recomputed normals 13.5


def normal_stats(vanilla: Path, built: Path) -> dict:
    addon = T.tool_dir(T.require("ueformat-blender"))
    return run_blender(["normals", str(addon), str(vanilla), str(built)], timeout=1800)


def normals_problem(stats: dict) -> list[str]:
    """Edits change normals only where geometry moved; a high 95th percentile means the whole mesh was re-shaded."""
    p95 = stats.get("p95")
    if p95 is None:
        return ["normals: no matching vertices between vanilla and the built mesh"]
    if p95 > NORMALS_P95_MAX:
        return [f"normals: 95% of corners within {p95} deg of vanilla (max {NORMALS_P95_MAX}): normals were recomputed "
                "on import, seams shade faceted"]
    return []


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
