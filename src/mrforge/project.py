"""Mod projects: scaffold, find, version bump. Manifest = mrforge.json at the project root."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .home import projects_root
from .util import ForgeError, UsageError, load_json, pak_name, save_json, slugify

MANIFEST = "mrforge.json"
LAYOUT = ("vanilla", "work/textures", "work/materials", "work/sources", "build", "dist")
KINDS = ("texture", "material", "mesh")


def new(name: str, skin: dict, kinds: list[str], changelist: int | None, out: str | None = None,
        description: str = "") -> Path:
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        raise UsageError(f"unknown kind(s) {bad}", f"use one or more of {', '.join(KINDS)}")
    slug = slugify(name)
    root = Path(out) if out else projects_root() / slug
    if (root / MANIFEST).exists():
        raise ForgeError("PROJECT_EXISTS", f"{root} already has {MANIFEST}", "pick another name or --out")
    for d in LAYOUT:
        (root / d).mkdir(parents=True, exist_ok=True)
    m = {"schema": 1, "id": slug, "name": name, "pak_name": pak_name(name), "version": "0.1.0",
         "hero": skin.get("hero", ""), "hero_id": skin["hero_id"], "skin": skin.get("skin", ""),
         "skin_id": skin["skin_id"], "kinds": kinds, "game_changelist": changelist,
         "description": description, "adds": [], "allow": [], "evidence": [],
         "created": time.strftime("%Y-%m-%d")}
    save_json(root / MANIFEST, m)
    (root / "CHANGELOG.md").write_text(f"# Changelog - {name}\n\n## 0.1.0 - {m['created']}\n\n- Project created for skin "
                                       f"{skin['skin_id']} {m['hero']} {m['skin']}.\n", encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text("build/\nvanilla/\n", encoding="utf-8", newline="\n")
    return root


def find(arg: str | None = None) -> Path:
    if arg:
        p = Path(arg)
        if (p / MANIFEST).is_file():
            return p.resolve()
        if p.name == MANIFEST and p.is_file():
            return p.parent.resolve()
        raise ForgeError("PROJECT_NOT_FOUND", f"{p} has no {MANIFEST}", "pass --project <folder with mrforge.json>")
    cur = Path.cwd().resolve()
    for d in (cur, *cur.parents):
        if (d / MANIFEST).is_file():
            return d
    raise ForgeError("PROJECT_NOT_FOUND", f"no {MANIFEST} in {cur} or its parents",
                     "cd into a project or pass --project; create one with mrforge new")


def manifest(root: Path) -> dict:
    return load_json(Path(root) / MANIFEST)


def save_manifest(root: Path, m: dict) -> None:
    save_json(Path(root) / MANIFEST, m)


def bump(root: Path, part: str = "patch", note: str = "") -> dict:
    m = manifest(root)
    mt = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", m["version"])
    if not mt:
        raise ForgeError("BAD_VERSION", f"version {m['version']!r} is not X.Y.Z")
    a, b, c = (int(x) for x in mt.groups())
    a, b, c = {"major": (a + 1, 0, 0), "minor": (a, b + 1, 0), "patch": (a, b, c + 1)}[part]
    old, m["version"] = m["version"], f"{a}.{b}.{c}"
    save_manifest(root, m)
    cl = Path(root) / "CHANGELOG.md"
    text = cl.read_text(encoding="utf-8") if cl.is_file() else f"# Changelog - {m['name']}\n"
    head, _, rest = text.partition("\n## ")
    entry = f"## {m['version']} - {time.strftime('%Y-%m-%d')}\n\n- {note or 'Changes.'}\n"
    cl.write_text(head.rstrip("\n") + "\n\n" + entry + ("\n## " + rest if rest else ""), encoding="utf-8", newline="\n")
    return {"old": old, "new": m["version"]}


def rel_project(root: Path, p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(p)


def env_project() -> str | None:
    return os.environ.get("MRFORGE_PROJECT")
