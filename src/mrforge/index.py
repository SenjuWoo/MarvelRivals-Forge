"""Installed-truth index: every vanilla package under a Characters/ path, per game build.

Built from `UAssetTool list_iostore <Paks dir> --filter Characters/`, which reads only the top-level game
containers (never ~mods). Verified: the whole listing takes about 5 s on the build machine.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .home import home
from .tools import run_tool
from .util import EnvError, ForgeError, fwd

FILTER = "Characters/"
CONTAINER_RE = re.compile(r"^=== (?P<name>.+?) ===\s*$")
LINE_RE = re.compile(r"^\s+(?:\.\./)*(?P<path>\S.*?\.(?:uasset|umap))\s+\[(?P<bulk>[^\]]+)\]\s+\(export=(?P<export>[\d,]+)b"
                     r"(?:\s+bulk=(?P<bulksize>[\d,]+)b)?\)")


def index_path(changelist: int) -> Path:
    return home() / "cache" / "index" / f"{changelist}.json"


def parse_listing(text: str) -> dict:
    containers: list[str] = []
    packages: dict[str, list] = {}
    cur = -1
    for line in text.splitlines():
        m = CONTAINER_RE.match(line)
        if m:
            containers.append(m["name"])
            cur = len(containers) - 1
            continue
        m = LINE_RE.match(line)
        if m:
            bulk = 0 if m["bulk"].strip() == "no bulk" else 1
            packages[m["path"]] = [cur, bulk, int(m["export"].replace(",", "")),
                                   int((m["bulksize"] or "0").replace(",", ""))]
    return {"containers": containers, "packages": packages}


def build(paks_dir, changelist: int) -> dict:
    t = time.time()
    res = run_tool("uassettool", ["list_iostore", fwd(paks_dir), "--filter", FILTER], timeout=900)
    if res["rc"] != 0:
        raise ForgeError("INDEX_LIST_FAILED", (res["stdout"] + res["stderr"]).strip()[-400:], "run mrforge doctor")
    parsed = parse_listing(res["stdout"])
    if not parsed["packages"]:
        raise ForgeError("INDEX_EMPTY", "list_iostore returned no Characters/ packages",
                         "check the game path with mrforge game; the tool output format may have changed")
    idx = {"changelist": changelist, "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "filter": FILTER,
           "seconds": round(time.time() - t, 1), **parsed}
    p = index_path(changelist)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(idx, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)
    return idx


_LOADED: dict = {}


def load(changelist: int, required: bool = True) -> dict | None:
    if changelist in _LOADED:
        return _LOADED[changelist]
    p = index_path(changelist)
    if not p.is_file():
        if required:
            raise EnvError("INDEX_MISSING", f"no package index for build {changelist}", "run: mrforge index")
        return None
    idx = json.loads(p.read_text(encoding="utf-8"))
    idx["_lower"] = {k.lower(): k for k in idx["packages"]}
    _LOADED[changelist] = idx
    return idx


def norm_pkg(path: str) -> str:
    s = path.replace("\\", "/").strip()
    while s.startswith("../"):
        s = s[3:]
    if s.startswith("/Game/"):
        s = "Marvel/Content/" + s[len("/Game/"):]
    if not s.endswith((".uasset", ".umap")):
        s += ".uasset"
    return s


def exists(idx: dict, path: str) -> bool:
    return norm_pkg(path).lower() in idx["_lower"]


def skin_packages(idx: dict, skin_id: str) -> list[dict]:
    hero = str(skin_id)[:4]
    needle = f"/characters/{hero}/{skin_id}/"
    out = []
    for low, real in idx["_lower"].items():
        if needle in low:
            c, bulk, exp, bsz = idx["packages"][real]
            out.append({"path": real, "container": idx["containers"][c] if c >= 0 else None,
                        "bulk": bool(bulk), "export_size": exp, "bulk_size": bsz})
    return sorted(out, key=lambda x: x["path"])


def classify(path: str) -> str:
    name = Path(path).stem
    low = path.lower()
    if "/vfx/" in low:
        return "vfx"
    if name.startswith("SK_") and name.endswith(("_Skeleton",)):
        return "skeleton"
    if name.endswith("_PhysicsAsset") or (name.startswith("Post_") and name.endswith("_Physics")) or name.endswith("_Physics"):
        return "physics"
    if name.startswith("SK_"):
        return "mesh"
    if name.startswith(("MI_", "M_")):
        return "material"
    if name.startswith("T_"):
        return "texture"
    return "other"


def skins_in_index(idx: dict) -> dict[str, int]:
    """skin id -> package count for every <hero>/<skin> folder under Marvel/Characters."""
    out: dict[str, int] = {}
    rx = re.compile(r"^marvel/content/marvel/characters/(\d{4})/(\d{7})/")
    for low in idx["_lower"]:
        m = rx.match(low)
        if m:
            out[m.group(2)] = out.get(m.group(2), 0) + 1
    return out
