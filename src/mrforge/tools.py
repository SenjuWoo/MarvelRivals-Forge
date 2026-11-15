"""Pinned upstream tools: resolve (installed -> --from copy -> download), verify by hash, probe, run.

The lock (tools.lock.json at the repository root) names each tool's release asset and the SHA-256 of
both the asset and the main executable. Nothing is ever installed system-wide and no installer runs.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .home import forge_root, home
from .util import EnvError, ForgeError, load_json, run, sha256_file

USER_AGENT = "mrforge"


def lock(path: Path | None = None) -> dict:
    p = path or forge_root() / "tools.lock.json"
    return load_json(p)


def entry(name: str, lk: dict | None = None) -> dict:
    lk = lk or lock()
    for t in lk["tools"]:
        if t["name"] == name:
            return t
    raise ForgeError("UNKNOWN_TOOL", f"{name} is not in tools.lock.json")


def tool_dir(t: dict) -> Path:
    return home() / "tools" / t["name"] / t["tag"]


def exe_path(t: dict) -> Path:
    return tool_dir(t) / t["exe"]


def asset_url(t: dict) -> str:
    return t.get("url") or f"https://github.com/{t['repo']}/releases/download/{t['tag']}/{t['asset']}"


def _shim(name: str) -> str | None:
    """Tests replace a tool with a Python script: MRFORGE_SHIM_<NAME>=<script>."""
    return os.environ.get("MRFORGE_SHIM_" + name.upper().replace("-", "_"))


def status(t: dict) -> dict:
    shim = _shim(t["name"])
    if shim:
        return {"name": t["name"], "tag": t["tag"], "installed": True, "hash_ok": True, "path": shim, "shim": True}
    p = exe_path(t)
    if not p.is_file():
        return {"name": t["name"], "tag": t["tag"], "installed": False, "hash_ok": False, "path": str(p)}
    ok = sha256_file(p) == t["exe_sha256"]
    return {"name": t["name"], "tag": t["tag"], "installed": True, "hash_ok": ok, "path": str(p)}


def require(name: str) -> dict:
    t = entry(name)
    st = status(t)
    if not st["installed"]:
        raise EnvError("TOOL_MISSING", f"{name} {t['tag']} is not set up", "run: mrforge setup")
    if not st["hash_ok"]:
        raise EnvError("TOOL_HASH_MISMATCH", f"{name} at {st['path']} does not match the pinned hash",
                       "run: mrforge setup --force")
    return t


def argv_for(name: str) -> list[str]:
    shim = _shim(name)
    if shim:
        return [sys.executable, shim]
    t = require(name)
    return [str(exe_path(t))]


def run_tool(name: str, args: list, cwd=None, timeout: float | None = 1800) -> dict:
    t = entry(name) if not _shim(name) else {"name": name}
    if not cwd and not _shim(name):
        cwd = str(tool_dir(t))  # UAssetTool drops oo2core next to itself; keep stray files out of the caller's cwd
    res = run(argv_for(name) + [str(a) for a in args], cwd=cwd, timeout=timeout)
    res["tool"] = name
    return res


def probe(t: dict) -> dict:
    if not t.get("probe"):
        st = status(t)
        return {"ok": st["installed"] and st["hash_ok"], "output": "file check only"}
    try:
        res = run_tool(t["name"], t["probe"], timeout=60)
    except ForgeError as e:
        return {"ok": False, "output": e.message}
    text = (res["stdout"] + res["stderr"]).strip()
    first = next((ln for ln in text.splitlines() if t["probe_expect"] in ln), text.splitlines()[0] if text else "")
    return {"ok": t["probe_expect"] in text, "output": first[:200]}


# --- resolution -------------------------------------------------------------

def _find_in(dirs: list[Path], t: dict, depth: int = 4) -> Path | None:
    """A tool root under one of dirs whose main executable has the pinned hash."""
    exe_rel = Path(t["exe"])
    base = exe_rel.name
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        start = len(d.parts)
        for dirpath, dirnames, filenames in os.walk(d):
            if len(Path(dirpath).parts) - start >= depth:
                dirnames[:] = []
            dirnames.sort()
            if base in filenames:
                cand = Path(dirpath) / base
                try:
                    if sha256_file(cand) != t["exe_sha256"]:
                        continue
                except OSError:
                    continue
                root = cand
                for _ in exe_rel.parts:
                    root = root.parent
                if (root / exe_rel).is_file():
                    return root
    return None


def _download(url: str, dest: Path, fetch=None) -> None:
    if fetch:
        dest.write_bytes(fetch(url))
        return
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for m in zf.infolist():
        target = (dest / m.filename).resolve()
        if dest != target and dest not in target.parents:
            raise ForgeError("UNSAFE_ARCHIVE", f"archive entry escapes the target folder: {m.filename}")
    zf.extractall(dest)


def _flatten(dest: Path, exe_rel: str) -> None:
    """Release zips often wrap everything in one folder; lift it so exe sits at its lock path."""
    if (dest / exe_rel).exists():
        return
    kids = [p for p in dest.iterdir()]
    if len(kids) == 1 and kids[0].is_dir() and (kids[0] / exe_rel).exists():
        inner = kids[0]
        for p in inner.iterdir():
            shutil.move(str(p), str(dest / p.name))
        inner.rmdir()


def resolve(t: dict, from_dirs: list[Path] | None = None, offline: bool = False, force: bool = False,
            fetch=None) -> dict:
    target = tool_dir(t)
    st = status(t)
    if st.get("shim"):
        return {"name": t["name"], "source": "shim", "path": st["path"]}
    if st["installed"] and st["hash_ok"] and not force:
        return {"name": t["name"], "source": "installed", "path": st["path"]}
    found = _find_in(from_dirs or [], t)
    if found:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(found, target)
        return {"name": t["name"], "source": "from", "from": str(found), "path": str(exe_path(t))}
    if offline:
        raise EnvError("TOOL_UNAVAILABLE_OFFLINE", f"{t['name']} {t['tag']} is not installed and --offline was given",
                       "run mrforge setup without --offline, or pass --from <folder with a matching copy>")
    cache = home() / "tools" / "_downloads"
    cache.mkdir(parents=True, exist_ok=True)
    zpath = cache / t["asset"]
    if not zpath.is_file() or sha256_file(zpath) != t["asset_sha256"]:
        _download(asset_url(t), zpath, fetch)
    got = sha256_file(zpath)
    if got != t["asset_sha256"]:
        zpath.unlink(missing_ok=True)
        raise ForgeError("TOOL_ASSET_HASH_MISMATCH", f"{t['asset']} hash {got[:16]}... != pinned {t['asset_sha256'][:16]}...",
                         "the upstream release changed; review it and update tools.lock.json")
    tmp = Path(tempfile.mkdtemp(prefix="mrf-", dir=str(cache)))
    try:
        with zipfile.ZipFile(zpath) as zf:
            _safe_extract(zf, tmp)
        _flatten(tmp, t["exe"])
        if not (tmp / t["exe"]).is_file():
            raise ForgeError("TOOL_LAYOUT_CHANGED", f"{t['asset']} has no {t['exe']}", "update tools.lock.json")
        if sha256_file(tmp / t["exe"]) != t["exe_sha256"]:
            raise ForgeError("TOOL_EXE_HASH_MISMATCH", f"{t['exe']} inside {t['asset']} does not match the pinned hash",
                             "update tools.lock.json after reviewing the release")
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(target))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return {"name": t["name"], "source": "download", "url": asset_url(t), "path": str(exe_path(t))}


def setup(from_dirs: list[str] | None = None, offline: bool = False, force: bool = False,
          only: list[str] | None = None, fetch=None, lk: dict | None = None) -> dict:
    lk = lk or lock()
    results, errors = [], []
    for t in lk["tools"]:
        if only and t["name"] not in only:
            continue
        if t.get("platform") == "windows" and os.name != "nt" and not _shim(t["name"]):
            results.append({"name": t["name"], "source": "skipped", "reason": "windows-only tool"})
            continue
        try:
            r = resolve(t, [Path(d) for d in from_dirs or []], offline, force, fetch)
            r["probe"] = probe(t)
            results.append(r)
        except ForgeError as e:
            errors.append({"tool": t["name"], **e.as_dict()})
    oodle = None
    try:
        ua = entry("uassettool", lk)
        dll = tool_dir(ua) / "oo2core_9_win64.dll"
        oodle = {"present": dll.is_file(), "path": str(dll),
                 "note": "UAssetTool downloads this DLL itself on its first extraction when missing"}
    except ForgeError:
        pass
    return {"tools": results, "errors": errors, "oodle": oodle}
