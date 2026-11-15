"""Find the installed game and read its layout, build, loader and mod-manager state."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .home import config
from .util import EnvError, load_json

APPID = "2767030"
GAME_EXE = "Marvel-Win64-Shipping.exe"


def steam_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(Path(winreg.QueryValueEx(k, val)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
        pf = os.environ.get("ProgramFiles(x86)")
        if pf:
            roots.append(Path(pf) / "Steam")
    else:
        roots += [Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"]
    seen, out = set(), []
    for r in roots:
        k = str(r).lower()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def library_paths(steam_root: Path) -> list[Path]:
    """Library folders from libraryfolders.vdf ("path" keys), plus the Steam root itself."""
    libs = [Path(steam_root)]
    vdf = Path(steam_root) / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            libs.append(Path(m.group(1).replace("\\\\", "\\")))
    return libs


def find_in_steam(roots: list[Path] | None = None) -> Path | None:
    for root in roots if roots is not None else steam_roots():
        for lib in library_paths(root):
            acf = lib / "steamapps" / f"appmanifest_{APPID}.acf"
            if acf.is_file():
                m = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text(encoding="utf-8", errors="replace"))
                if m:
                    p = lib / "steamapps" / "common" / m.group(1)
                    if is_game_root(p):
                        return p
    return None


def is_game_root(p: Path) -> bool:
    return (Path(p) / "MarvelGame" / "Marvel" / "Content" / "Paks").is_dir()


def find_game(explicit: str | None = None) -> tuple[Path, str]:
    """Return (root, source). Order: --game > MRFORGE_GAME > config > Steam."""
    for value, source in ((explicit, "--game"), (os.environ.get("MRFORGE_GAME"), "MRFORGE_GAME"),
                          (config().get("game"), "config")):
        if value:
            p = Path(value)
            if not is_game_root(p):
                raise EnvError("GAME_NOT_FOUND", f"{source} points at {p}, which has no MarvelGame/Marvel/Content/Paks",
                               "pass --game <folder that contains MarvelGame>")
            return p, source
    p = find_in_steam()
    if p:
        return p, "steam"
    raise EnvError("GAME_NOT_FOUND", "Marvel Rivals was not found in any Steam library",
                   "pass --game <install folder> or set MRFORGE_GAME")


def layout(root: Path) -> dict:
    mg = Path(root) / "MarvelGame"
    paks = mg / "Marvel" / "Content" / "Paks"
    return {"root": Path(root), "paks_dir": paks, "mods_dir": paks / "~mods",
            "win64_dir": mg / "Marvel" / "Binaries" / "Win64", "version_file": mg / "version.json"}


def version(root: Path) -> dict:
    vf = layout(root)["version_file"]
    try:
        v = load_json(vf)
    except (FileNotFoundError, ValueError) as e:
        raise EnvError("GAME_VERSION_UNREADABLE", f"cannot read {vf}: {e}", "verify the game files in Steam") from e
    return {"version": v.get("version"), "changelist": int(v["changelist"]) if v.get("changelist") else None}


def loader(root: Path) -> dict:
    w = layout(root)["win64_dir"]
    plugins = w / "plugins"
    asi = sorted(p.name for p in plugins.glob("*.asi")) if plugins.is_dir() else []
    dsound = (w / "dsound.dll").is_file()
    bypass = [a for a in asi if "bypass" in a.lower() or "sig" in a.lower()]
    return {"asi_loader": dsound, "asi_plugins": asi, "signature_bypass": bool(bypass),
            "present": dsound and bool(bypass)}


def mod_manager(root: Path) -> dict:
    lay = layout(root)
    markers = []
    for d in (lay["paks_dir"], lay["mods_dir"]):
        if d.is_dir():
            for p in d.iterdir():
                if p.name.startswith("vortex.deployment.") or p.name == "__folder_managed_by_vortex":
                    markers.append(p.name)
    load_order = sorted(p.name for p in Path(root).glob("*_loadOrder.json"))
    return {"vortex": bool(markers or load_order), "markers": sorted(set(markers)), "load_order_files": load_order}


def game_running() -> bool:
    if os.name != "nt":
        return False
    try:
        p = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH"], capture_output=True,
                           timeout=20, stdin=subprocess.DEVNULL)
        return GAME_EXE.lower() in p.stdout.decode("utf-8", errors="replace").lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def info(explicit: str | None = None) -> dict:
    root, source = find_game(explicit)
    lay = layout(root)
    mods = lay["mods_dir"]
    return {"root": str(root), "source": source, "paks_dir": str(lay["paks_dir"]), "mods_dir": str(mods),
            "win64_dir": str(lay["win64_dir"]), **version(root), "loader": loader(root),
            "mod_manager": mod_manager(root), "running": game_running(),
            "mods_dir_exists": mods.is_dir()}
