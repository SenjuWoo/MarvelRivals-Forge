"""Build artifacts/MarvelRivals-Forge-<version>.zip from tracked files only (git ls-files), deterministically.

Writes SHA256SUMS, manifest.json (file list with hashes) and build-receipt.json next to the zip.
Usage: python tools/build_release.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED = (1980, 1, 1, 0, 0, 0)
NEVER = ("LOCAL.md", ".mrforge/", "projects/", "artifacts/", ".venv/")


def version() -> str:
    text = (ROOT / "src" / "mrforge" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    files = sorted(f for f in out.decode("utf-8").split("\0") if f)
    bad = [f for f in files if f.startswith(NEVER) or f in NEVER]
    if bad:
        sys.exit(f"refusing to package private paths: {bad}")
    return files


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ver = version()
    files = tracked()
    out_dir = ROOT / "artifacts"
    out_dir.mkdir(exist_ok=True)
    name = f"MarvelRivals-Forge-{ver}"
    zpath = out_dir / f"{name}.zip"
    manifest = []
    tmp = zpath.with_name(zpath.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in files:
            data = (ROOT / f).read_bytes()
            # Normalise text line endings the way .gitattributes checks them out, so archives match across OSes.
            if b"\0" not in data[:4096]:
                lf = data.replace(b"\r\n", b"\n")
                data = lf.replace(b"\n", b"\r\n") if f.lower().endswith((".bat", ".cmd", ".ps1")) else lf
            zi = zipfile.ZipInfo(f"{name}/{f}", date_time=FIXED)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zi.create_system = 0
            zf.writestr(zi, data)
            manifest.append({"path": f, "sha256": sha(data), "size": len(data)})
    tmp.replace(zpath)
    zsha = sha(zpath.read_bytes())
    (out_dir / "SHA256SUMS").write_text(f"{zsha}  {zpath.name}\n", encoding="utf-8", newline="\n")
    (out_dir / "manifest.json").write_text(json.dumps({"version": ver, "files": manifest}, indent=1) + "\n",
                                           encoding="utf-8", newline="\n")
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    (out_dir / "build-receipt.json").write_text(json.dumps({"version": ver, "commit": commit, "dirty": dirty,
                                                            "zip": zpath.name, "sha256": zsha, "files": len(files)},
                                                           indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"zip": str(zpath), "sha256": zsha, "files": len(files), "commit": commit, "dirty": dirty}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
