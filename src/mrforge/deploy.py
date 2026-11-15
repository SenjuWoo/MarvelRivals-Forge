"""mrforge deploy / undeploy / status: copy the triple into Paks/~mods/<prefix>-mrforge-<id>/ with a receipt.

The only write the forge makes into the game folder. Undeploy removes only files listed in the receipt whose
hash still matches, then the folder if it is empty. No other folder is ever touched (decision D10).
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import project as P
from .build import triple
from .game import find_game, game_running, layout
from .home import config, home
from .util import ForgeError, load_json, save_json, sha256_file


def receipt_path(mod_id: str) -> Path:
    return home() / "receipts" / f"{mod_id}.json"


def folder_name(prefix: str, mod_id: str) -> str:
    return f"{prefix}-mrforge-{mod_id}"


def deploy(root: Path, prefix: str | None = None, game_arg=None, running=None) -> dict:
    root = Path(root)
    m = P.manifest(root)
    tr = triple(root, m)
    missing = [p.name for p in tr.values() if not p.is_file()]
    if missing:
        raise ForgeError("NOT_BUILT", f"missing {missing}", "mrforge build && mrforge validate")
    if (running if running is not None else game_running()):
        raise ForgeError("GAME_RUNNING", "the game is running; files in ~mods are read at startup and may be locked",
                         "close Marvel Rivals and retry")
    groot, _ = find_game(game_arg)
    mods_dir = layout(groot)["mods_dir"]
    prefix = prefix or config().get("deploy_prefix") or "ZZZ"
    old = load_json(receipt_path(m["id"]), {})
    if old.get("folder") and Path(old["folder"]).name != folder_name(prefix, m["id"]):
        undeploy(m["id"], running=False)
    dest = mods_dir / folder_name(prefix, m["id"])
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    for p in tr.values():
        target = dest / p.name
        shutil.copyfile(p, target)
        files.append({"path": str(target), "sha256": sha256_file(target)})
    rec = {"mod": m["id"], "version": m["version"], "project": str(root), "folder": str(dest), "files": files,
           "deployed": time.strftime("%Y-%m-%dT%H:%M:%S"), "game_root": str(groot)}
    save_json(receipt_path(m["id"]), rec)
    return {"folder": str(dest), "files": [f["path"] for f in files],
            "next": f"start the game, look at the skin in the lobby, then: mrforge check-load {m['id']}"}


def undeploy(mod_id: str, running=None) -> dict:
    rec = load_json(receipt_path(mod_id), {})
    if not rec:
        raise ForgeError("NOT_DEPLOYED", f"no deploy receipt for {mod_id}", "mrforge deploy --status")
    if (running if running is not None else game_running()):
        raise ForgeError("GAME_RUNNING", "the game is running", "close Marvel Rivals and retry")
    removed, kept = [], []
    for f in rec["files"]:
        p = Path(f["path"])
        if not p.is_file():
            continue
        if sha256_file(p) == f["sha256"]:
            p.unlink()
            removed.append(str(p))
        else:
            kept.append({"path": str(p), "reason": "changed since deploy; left in place"})
    folder = Path(rec["folder"])
    folder_removed = False
    if folder.is_dir() and not any(folder.iterdir()) and "-mrforge-" in folder.name:
        folder.rmdir()
        folder_removed = True
    receipt_path(mod_id).unlink(missing_ok=True)
    return {"removed": removed, "kept": kept, "folder_removed": folder_removed}


def status() -> dict:
    out = []
    for p in sorted((home() / "receipts").glob("*.json")):
        rec = load_json(p)
        files_ok = all(Path(f["path"]).is_file() and sha256_file(Path(f["path"])) == f["sha256"] for f in rec["files"])
        out.append({"mod": rec["mod"], "version": rec.get("version"), "folder": rec["folder"], "intact": files_ok,
                    "deployed": rec.get("deployed")})
    return {"deployed": out}
