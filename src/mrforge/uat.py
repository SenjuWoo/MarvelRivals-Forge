"""UAssetTool wrappers and parsers for its text output (formats captured from v1.5.9 on 2026-11-15)."""
from __future__ import annotations

import re
from pathlib import Path

from .tools import run_tool
from .util import ForgeError, fwd

ITEM_RE = re.compile(r"^\s*(?P<rel>\S.*?\.uasset) \.\.\. ?(?P<rest>.*)$")
TEX_RE = re.compile(r"Texture: (?P<w>\d+)x(?P<h>\d+), format=(?P<fmt>\S+)")
MIPS_RE = re.compile(r"Mip count: (?P<n>\d+)")
SAVED_RE = re.compile(r"Saved: (?P<p>.+?)\s*$")
DIM_RE = re.compile(r"Dimensions: (?P<w>\d+)x(?P<h>\d+)")
PF_RE = re.compile(r"Pixel Format: (?P<fmt>\S+)")


def parse_batch_textures(text: str) -> list[dict]:
    out: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = ITEM_RE.match(line)
        if m:
            cur = {"rel": m["rel"].replace("\\", "/"), "ok": False}
            out.append(cur)
            if "SKIP" in m["rest"]:
                cur["skip"] = True
            line = m["rest"]
        if cur is None:
            continue
        t = TEX_RE.search(line)
        if t:
            cur.update(width=int(t["w"]), height=int(t["h"]), format=t["fmt"])
        mm = MIPS_RE.search(line)
        if mm:
            cur["mips"] = int(mm["n"])
        s = SAVED_RE.search(line)
        if s:
            cur["saved"] = s["p"].replace("\\", "/")
        if line.strip().startswith("OK ("):
            cur["ok"] = True
        if "ERROR" in line or "Failed" in line:
            cur["error"] = line.strip()[:200]
    return [r for r in out if not r.get("skip")]


def parse_extract_texture(text: str) -> dict:
    d: dict = {}
    m = DIM_RE.search(text) or TEX_RE.search(text)
    if m:
        d["width"], d["height"] = int(m["w"]), int(m["h"])
    m = PF_RE.search(text) or TEX_RE.search(text)
    if m:
        d["format"] = m["fmt"]
    m = re.search(r"Mip Count: (\d+)", text) or MIPS_RE.search(text)
    if m:
        d["mips"] = int(m.group(1))
    d["ok"] = "Success!" in text
    return d


SLOT_RE = re.compile(r"^\s+\[(?P<i>\d+)\] MaterialInterface: (?P<ref>-?\d+)")


def parse_mesh_info(text: str) -> dict:
    mats: list[dict] = []
    cur = None
    in_tags = False
    count = None
    for line in text.splitlines():
        m = re.match(r"^\s+=== Materials \((\d+)\) ===", line)
        if m:
            count = int(m.group(1))
            continue
        m = SLOT_RE.match(line)
        if m:
            cur = {"index": int(m["i"]), "slot": None, "imported": None, "tags": []}
            mats.append(cur)
            in_tags = False
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("SlotName:"):
            cur["slot"] = s.split(":", 1)[1].strip()
        elif s.startswith("ImportedSlotName:"):
            cur["imported"] = s.split(":", 1)[1].strip()
        elif s.startswith("GameplayTags:"):
            in_tags = True
        elif in_tags and s.startswith("- "):
            cur["tags"].append(s[2:].strip())
        elif s.startswith("==="):
            cur = None
            in_tags = False
    return {"material_count": count if count is not None else len(mats), "materials": mats}


def extract_vanilla(paks_dir, out_dir, patterns: list[str], mod: str | None = None, timeout=1800) -> dict:
    """extract_iostore_legacy. Patterns go through a file when long (Windows command-line limit)."""
    if not patterns:
        raise ForgeError("NOTHING_SELECTED", "no packages selected for extraction")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    args = ["extract_iostore_legacy", fwd(paks_dir), fwd(out_dir)]
    if len(patterns) > 20:
        lst = out_dir.parent / (out_dir.name + ".filters.txt")
        lst.write_text("\n".join(patterns) + "\n", encoding="utf-8")
        args += ["--filter", fwd(lst)]
    else:
        args += ["--filter", *patterns]
    if mod:
        args += ["--mod", fwd(mod)]
    res = run_tool("uassettool", args, timeout=timeout)
    text = res["stdout"] + res["stderr"]
    m = re.search(r"Extraction complete: (\d+) converted, (\d+) failed", text)
    res["converted"] = int(m.group(1)) if m else 0
    res["failed"] = int(m.group(2)) if m else None
    if res["rc"] != 0 or not m:
        raise ForgeError("EXTRACT_FAILED", text.strip()[-500:] or f"rc {res['rc']}", "run mrforge doctor; check the filter paths")
    return res


def pattern_for(pkg_path: str) -> str:
    """Filter pattern for one package: its path without extension (substring match in the tool)."""
    p = pkg_path
    for ext in (".uasset", ".umap"):
        if p.endswith(ext):
            p = p[: -len(ext)]
    return p
