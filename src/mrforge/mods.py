"""Installed mods in Paks/~mods: package lists (retoc manifest --filters), container flags, conflicts.

Read-only. Results are cached per file by size + mtime so repeated scans are fast.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .home import home
from .tools import run_tool
from .util import load_json, save_json

FLAGS_RE = re.compile(r"container_flags:\s*EIoContainerFlags\(([^)]*)\)")


def _cache_path() -> Path:
    return home() / "cache" / "mods.json"


def parse_info(text: str) -> dict:
    """Fields from `retoc-rivals-cli info`. IoStore prints container_flags; legacy paks print key: value lines."""
    out: dict = {}
    m = FLAGS_RE.search(text)
    if m:
        out["flags"] = [f.strip() for f in m.group(1).split("|") if f.strip()]
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("type:"):
            out["type"] = s.split(":", 1)[1].strip()
        elif s.startswith("encrypted index:"):
            out["encrypted_index"] = s.split(":", 1)[1].strip().lower() == "true"
        elif s.startswith("packages:"):
            try:
                out["package_count"] = int(s.split(":", 1)[1])
            except ValueError:
                pass
    return out


def parse_filters(text: str) -> list[str]:
    """Package paths from `manifest --filters`, normalised to Marvel/Content/... (no ../../../)."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or not s.endswith((".uasset", ".umap")):
            continue
        while s.startswith("../"):
            s = s[3:]
        out.append(s)
    return sorted(set(out))


def bad_flags(rec: dict) -> list[str]:
    bad = []
    if "Encrypted" in rec.get("flags", []) or rec.get("encrypted_index"):
        bad.append("encrypted")
    if rec.get("error"):
        bad.append("unreadable (obfuscated or stripped?)")
    return bad


def _inspect(path: Path) -> dict:
    rec: dict = {}
    info = run_tool("retoc-rivals-cli", ["info", str(path)], timeout=120)
    text = info["stdout"] + info["stderr"]
    if info["rc"] != 0:
        rec["error"] = text.strip().splitlines()[-1][:300] if text.strip() else f"rc {info['rc']}"
        return rec
    rec.update(parse_info(text))
    if path.suffix.lower() == ".utoc":
        man = run_tool("retoc-rivals-cli", ["manifest", "--filters", str(path)], timeout=300)
        if man["rc"] == 0:
            rec["packages"] = parse_filters(man["stdout"])
        else:
            rec["error"] = (man["stdout"] + man["stderr"]).strip()[-300:]
    return rec


def scan(mods_dir, use_cache: bool = True, exclude_prefix: str | None = None) -> list[dict]:
    mods_dir = Path(mods_dir)
    if not mods_dir.is_dir():
        return []
    cache = load_json(_cache_path(), {}) if use_cache else {}
    out, fresh = [], {}
    for dirpath, dirnames, filenames in os.walk(mods_dir):
        dirnames.sort()
        names = set(filenames)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            low = fn.lower()
            if low.endswith(".utoc"):
                target = p
            elif low.endswith(".pak") and fn[:-4] + ".utoc" not in names:
                target = p  # legacy pak without IoStore companion
            else:
                continue
            st = p.stat()
            key = str(p)
            c = cache.get(key)
            if c and c.get("size") == st.st_size and c.get("mtime") == int(st.st_mtime):
                rec = c
            else:
                rec = {"size": st.st_size, "mtime": int(st.st_mtime), **_inspect(p)}
            fresh[key] = rec
            folder = Path(dirpath).relative_to(mods_dir).as_posix() if Path(dirpath) != mods_dir else "."
            item = {"name": Path(fn).stem, "folder": folder, "path": key, "kind": "iostore" if target.suffix.lower() == ".utoc" else "legacy-pak",
                    "flags": rec.get("flags", []), "packages": rec.get("packages", []),
                    "package_count": rec.get("package_count", len(rec.get("packages", [])))}
            if rec.get("error"):
                item["error"] = rec["error"]
            fb = bad_flags(rec)
            if fb:
                item["flags_bad"] = fb
            out.append(item)
    if exclude_prefix:
        out = [m for m in out if not m["folder"].startswith(exclude_prefix)]
    save_json(_cache_path(), fresh)
    return out


def package_owners(mods: list[dict]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for m in mods:
        for p in m["packages"]:
            owners.setdefault(p.lower(), []).append(m["folder"] + "/" + m["name"])
    return owners


def conflicts(mods: list[dict], only_packages: list[str] | None = None) -> list[dict]:
    owners = package_owners(mods)
    out = []
    if only_packages is not None:
        for p in only_packages:
            o = owners.get(p.lower(), [])
            if o:
                out.append({"package": p, "mods": o})
        return out
    for p, o in sorted(owners.items()):
        if len(o) > 1:
            out.append({"package": p, "mods": o})
    return out
