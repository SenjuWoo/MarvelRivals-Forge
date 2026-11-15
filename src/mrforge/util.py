"""Shared helpers: named errors, JSON files, hashing, subprocesses, names."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = PKG_DIR / "knowledge"


class ForgeError(Exception):
    """An expected failure with a stable name and a fix. Exit 1 (or 3 for environment problems)."""

    def __init__(self, code: str, message: str, fix: str = "", exit_code: int = 1, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix
        self.exit_code = exit_code
        self.data = data or {}

    def as_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.fix:
            d["fix"] = self.fix
        return d


class EnvError(ForgeError):
    """Something outside the forge is missing or wrong (game, tool, mapping). Exit 3."""

    def __init__(self, code: str, message: str, fix: str = "", data: dict | None = None):
        super().__init__(code, message, fix, 3, data)


class UsageError(ForgeError):
    def __init__(self, message: str, fix: str = ""):
        super().__init__("USAGE", message, fix, 2)


def load_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def save_json(path: Path, value) -> None:
    """Atomic write: a crash never leaves a half-written JSON file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fwd(path) -> str:
    """Absolute path with forward slashes. UAssetTool rejects some relative output paths."""
    return str(Path(path).resolve()).replace("\\", "/")


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").lower()
    return s or "mod"


def pak_name(name: str) -> str:
    """Container base name: letters, digits and underscores only (retoc appends _9999999_P)."""
    parts = re.findall(r"[A-Za-z0-9]+", name)
    s = "".join(p[:1].upper() + p[1:] for p in parts)
    return s or "Mod"


def iter_files(root: Path):
    root = Path(root)
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for n in sorted(filenames):
            yield Path(dirpath) / n


def rel(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


_REDACT: list[str] = []


def add_redaction(secret: str) -> None:
    """Register a secret that must never reach output or logs."""
    if secret and secret not in _REDACT:
        _REDACT.append(secret)


def redact(text: str) -> str:
    for s in _REDACT:
        text = text.replace(s, "<redacted>")
    return text


def run(argv: list, cwd=None, timeout: float | None = 1800, env: dict | None = None) -> dict:
    """Run a process from an argv list (never a shell string). Returns rc, stdout, stderr, seconds."""
    argv = [str(a) for a in argv]
    t = time.time()
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, env=full_env,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise EnvError("TOOL_NOT_RUNNABLE", f"cannot start {argv[0]}: {e}", "run: mrforge setup") from e
    except subprocess.TimeoutExpired as e:
        raise ForgeError("TOOL_TIMEOUT", f"{Path(argv[0]).name} did not finish in {timeout}s",
                         "retry; if it repeats, run the same step with fewer files") from e
    out = p.stdout.decode("utf-8", errors="replace")
    err = p.stderr.decode("utf-8", errors="replace")
    res = {"rc": p.returncode, "stdout": out, "stderr": err, "seconds": round(time.time() - t, 2),
           "argv": [redact(a) for a in argv]}
    try:
        from .home import log_line
        log_line("proc", {"argv": res["argv"], "rc": p.returncode, "seconds": res["seconds"]})
    except Exception:  # logging must never break a build
        pass
    return res


def python_exe() -> str:
    return sys.executable
