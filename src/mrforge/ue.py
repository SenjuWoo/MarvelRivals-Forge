"""Detect Unreal Engine 5.3.2 (the game's engine version), needed only for the mesh-build route."""
from __future__ import annotations

import json
import os
import string
from pathlib import Path

from .home import config

WANT = (5, 3, 2)


def build_version(root: Path) -> tuple[int, int, int] | None:
    bv = Path(root) / "Engine" / "Build" / "Build.version"
    try:
        d = json.loads(bv.read_text(encoding="utf-8-sig"))
        return int(d["MajorVersion"]), int(d["MinorVersion"]), int(d["PatchVersion"])
    except (OSError, ValueError, KeyError):
        return None


def editor_cmd(root: Path) -> Path:
    return Path(root) / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"


def _candidates() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    if os.environ.get("MRFORGE_UE"):
        out.append((Path(os.environ["MRFORGE_UE"]), "MRFORGE_UE"))
    if config().get("ue_root"):
        out.append((Path(config()["ue_root"]), "config"))
    program_data = os.environ.get("ProgramData") or os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "ProgramData")
    dat = Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    try:
        for inst in json.loads(dat.read_text(encoding="utf-8-sig")).get("InstallationList", []):
            if str(inst.get("AppName", "")).startswith("UE_"):
                out.append((Path(inst["InstallLocation"]), "launcher"))
    except (OSError, ValueError):
        pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine\5.3") as k:
                out.append((Path(winreg.QueryValueEx(k, "InstalledDirectory")[0]), "registry"))
        except OSError:
            pass
        # Bounded scan of the usual install folders on each drive (no full-drive walk).
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if not drive.exists():
                continue
            for sub in (r"Program Files\Epic Games\UE_5.3", r"Epic Games\UE_5.3", r"Unreal Engine\UE_5.3",
                        r"Games\UE_5.3", "UE_5.3"):
                out.append((drive / sub, "scan"))
    return out


def detect() -> dict:
    seen = set()
    others = []
    for root, source in _candidates():
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        v = build_version(root)
        if v is None:
            continue
        if v == WANT and editor_cmd(root).is_file():
            return {"found": True, "root": str(root), "version": "%d.%d.%d" % v, "source": source,
                    "editor_cmd": str(editor_cmd(root))}
        others.append({"root": str(root), "version": "%d.%d.%d" % v})
    return {"found": False, "other_versions": others}
