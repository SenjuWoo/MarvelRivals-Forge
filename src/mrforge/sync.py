"""Mappings (.usmap) for the installed build and the game AES key, from the community depot.

Rule D12: the mapping must match the installed changelist exactly unless --allow-nearest is given,
because a wrong mapping misreads unversioned properties without any error.
The AES key is stored in .mrforge/keys.json and never printed or logged.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from .home import home
from .util import EnvError, ForgeError, add_redaction, load_json, save_json, sha256_bytes, sha256_file

DEPOT = "SpaceDepot/rivals-depot"
LIST_URL = f"https://api.github.com/repos/{DEPOT}/contents/usmap"
AES_URL = f"https://raw.githubusercontent.com/{DEPOT}/main/AES.json"
NAME_RE = re.compile(r"^(?P<engine>\d+\.\d+\.\d+)-(?P<build>\d+)\+\+\+depot_marvel\+S(?P<season>[\d._]+)_release-Marvel\.usmap$")


def default_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mrforge", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def usmap_dir() -> Path:
    return home() / "cache" / "usmap"


def cache_index() -> dict:
    return load_json(usmap_dir() / "index.json", {})


def parse_listing(raw: bytes) -> list[dict]:
    out = []
    for e in json.loads(raw):
        m = NAME_RE.match(e.get("name", ""))
        if m:
            out.append({"name": e["name"], "build": int(m["build"]), "season": m["season"],
                        "download_url": e.get("download_url"), "size": e.get("size")})
    return sorted(out, key=lambda x: x["build"])


def pick(entries: list[dict], changelist: int, allow_nearest: bool) -> tuple[dict, bool]:
    exact = [e for e in entries if e["build"] == changelist]
    if exact:
        return exact[0], True
    lower = [e for e in entries if e["build"] < changelist]
    nearest = lower[-1] if lower else None
    if allow_nearest and nearest:
        return nearest, False
    raise EnvError("USMAP_BUILD_MISMATCH",
                   f"no mapping for build {changelist}" + (f"; nearest lower is {nearest['build']} ({nearest['name']})" if nearest else ""),
                   "wait for the depot to publish this build, or rerun with --allow-nearest (property reads may be wrong)",
                   {"nearest": nearest["name"] if nearest else None})


def usmap_for(changelist: int, allow_nearest: bool = False) -> Path | None:
    idx = cache_index()
    for name, rec in idx.items():
        if rec["build"] == changelist and (usmap_dir() / name).is_file():
            return usmap_dir() / name
    if allow_nearest:
        lower = sorted((r["build"], n) for n, r in idx.items() if r["build"] < changelist and (usmap_dir() / n).is_file())
        if lower:
            return usmap_dir() / lower[-1][1]
    return None


def require_usmap(changelist: int, allow_nearest: bool = False) -> Path:
    p = usmap_for(changelist, allow_nearest)
    if not p:
        raise EnvError("USMAP_MISSING", f"no cached mapping for build {changelist}", "run: mrforge sync")
    return p


def aes_key() -> str | None:
    k = load_json(home() / "keys.json", {}).get("mainKey")
    if k:
        add_redaction(k)
    return k


def sync(changelist: int, fetch=None, offline: bool = False, allow_nearest: bool = False) -> dict:
    fetch = fetch or default_fetch
    d = usmap_dir()
    if offline:
        p = usmap_for(changelist, allow_nearest)
        if not p:
            raise EnvError("USMAP_MISSING", f"offline and no cached mapping for build {changelist}",
                           "run mrforge sync once while online")
        return {"usmap": p.name, "sha256": sha256_file(p), "exact": cache_index()[p.name]["build"] == changelist,
                "source": "cache", "aes_key": "present" if aes_key() else "missing"}
    try:
        entries = parse_listing(fetch(LIST_URL))
    except (OSError, ValueError) as e:
        cached = usmap_for(changelist, allow_nearest)
        if cached:
            return {"usmap": cached.name, "sha256": sha256_file(cached), "source": "cache",
                    "exact": cache_index()[cached.name]["build"] == changelist, "warning": f"depot unreachable: {e}",
                    "aes_key": "present" if aes_key() else "missing"}
        raise EnvError("DEPOT_UNREACHABLE", f"cannot list {LIST_URL}: {e}", "check the network and retry") from e
    chosen, exact = pick(entries, changelist, allow_nearest)
    path = d / chosen["name"]
    idx = cache_index()
    if not path.is_file() or idx.get(chosen["name"], {}).get("sha256") != sha256_file(path):
        data = fetch(chosen["download_url"])
        if len(data) < 1024:
            raise ForgeError("USMAP_DOWNLOAD_BAD", f"{chosen['name']} downloaded as {len(data)} bytes", "retry later")
        path.write_bytes(data)
        idx[chosen["name"]] = {"build": chosen["build"], "season": chosen["season"], "sha256": sha256_bytes(data)}
        save_json(d / "index.json", idx)
    key_state = "unchanged"
    try:
        key = json.loads(fetch(AES_URL)).get("mainKey")
        if key:
            add_redaction(key)
            save_json(home() / "keys.json", {"mainKey": key, "source": AES_URL})
            key_state = "stored"
    except (OSError, ValueError):
        key_state = "fetch_failed" if not aes_key() else "kept_cached"
    return {"usmap": chosen["name"], "build": chosen["build"], "season": chosen["season"], "exact": exact,
            "sha256": idx[chosen["name"]]["sha256"], "path": str(path), "source": "depot", "aes_key": key_state}
