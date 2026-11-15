"""mrforge build: changed textures -> inject_texture, changed materials -> from_json, staging -> retoc pack.

Only changed packages are staged. Output: dist/<PakName>_9999999_P.{pak,utoc,ucas} + dist/receipt.json.
Never obfuscated, stripped or encrypted (decision D8).
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import mat as M
from . import project as P
from . import tex as X
from . import tools as T
from .extract import load_lock
from .sync import require_usmap
from .tools import run_tool
from .util import ForgeError, fwd, iter_files, save_json, sha256_file

SUFFIX = "_9999999_P"
TRIPLE = (".pak", ".utoc", ".ucas")


def triple(root: Path, m: dict) -> dict[str, Path]:
    return {ext: Path(root) / "dist" / f"{m['pak_name']}{SUFFIX}{ext}" for ext in TRIPLE}


def _changed_materials(root: Path, lk: dict) -> list[str]:
    ops = M.load_ops(root)["materials"]
    out = set(k for k, v in ops.items() if v and k in lk["materials"])
    for k, rec in lk["materials"].items():
        w = Path(root) / rec["work_json"]
        if w.is_file() and sha256_file(w) != rec["json_sha256"]:
            out.add(k)
    return sorted(out)


def run(root: Path) -> dict:
    root = Path(root)
    m = P.manifest(root)
    lk = load_lock(root)
    usmap = require_usmap(lk["changelist"])
    t0 = time.time()
    regenerated = X.regenerate_all(root, lk)
    tex_changed = X.changed(root, lk)
    mat_changed = _changed_materials(root, lk)
    if not tex_changed and not mat_changed:
        raise ForgeError("NOTHING_TO_BUILD", "no texture or material differs from vanilla",
                         "edit something first: mrforge tex ... or mrforge mat set ...")
    stage_root = root / "build" / "stage"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage = stage_root / m["pak_name"]
    stage.mkdir(parents=True)
    staged, warnings, inputs = [], [], {}
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
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    for f in triple(root, m).values():
        f.unlink(missing_ok=True)
    r = run_tool("retoc-rivals-cli", ["pack", fwd(stage), "--output", fwd(dist)], timeout=1800)
    tr = triple(root, m)
    missing = [str(p.name) for p in tr.values() if not p.is_file()]
    if r["rc"] != 0 or missing:
        raise ForgeError("PACK_FAILED", f"retoc pack: {(r['stdout'] + r['stderr']).strip()[-500:]} missing={missing}",
                         "run mrforge doctor; inspect build/stage")
    tool_info = {}
    for name in ("uassettool", "retoc-rivals-cli"):
        t = T.entry(name)
        tool_info[name] = {"tag": t["tag"], "exe_sha256": t["exe_sha256"]}
    receipt = {"mod": m["id"], "name": m["name"], "version": m["version"], "skin_id": m["skin_id"],
               "changelist": lk["changelist"], "usmap": lk["usmap"], "usmap_sha256": lk["usmap_sha256"],
               "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "tools": tool_info,
               "staged_packages": sorted(staged), "inputs": inputs,
               "outputs": {p.name: sha256_file(p) for p in tr.values()},
               "pack_argv": r["argv"][1:], "options": {"obfuscate": False, "strip": False, "encrypt": False}}
    save_json(dist / "receipt.json", receipt)
    return {"packages": len(staged), "textures": tex_changed, "materials": mat_changed, "regenerated": len(regenerated),
            "outputs": [str(p) for p in tr.values()], "seconds": round(time.time() - t0, 1), "warnings": warnings,
            "stage_files": sum(1 for _ in iter_files(stage))}
