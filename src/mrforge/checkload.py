"""mrforge check-load: after an in-game test, check the deploy, the loader and the newest logs.

Load and gameplay tiers are owner-observed; --confirm records that observation in the project.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from . import project as P
from .deploy import receipt_path
from .game import find_game, loader
from .knowledge import errors
from .util import ForgeError, load_json, sha256_file


def log_dir() -> Path:
    env = os.environ.get("MRFORGE_LOG_DIR")
    if env:
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Marvel" / "Saved"


def newest_logs(d: Path) -> list[Path]:
    out = []
    logs = sorted((d / "Logs").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True) if (d / "Logs").is_dir() else []
    if logs:
        out.append(logs[0])
    if (d / "Galacta.log").is_file():
        out.append(d / "Galacta.log")
    return out


def scan_log(path: Path, pak_name: str | None, sigs: list[dict], limit: int = 30) -> dict:
    hits, mentions = [], []
    rx = [(s, re.compile(s["pattern"])) for s in sigs]
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            for s, r in rx:
                if r.search(line):
                    hits.append({"line": n, "signature": s["id"], "text": line.strip()[:240], "fix": s["fix"]})
                    break
            if pak_name and pak_name.lower() in line.lower():
                mentions.append({"line": n, "text": line.strip()[:240]})
    return {"log": str(path), "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime)),
            "signatures": hits[:limit], "mentions_of_mod": mentions[:limit]}


def run(mod_id: str | None, root: Path | None, game_arg=None, confirm: str | None = None, tier: str = "load") -> dict:
    m = P.manifest(root) if root else None
    mod_id = mod_id or (m["id"] if m else None)
    if not mod_id:
        raise ForgeError("NO_MOD", "no mod id given and no project here", "mrforge check-load <id>")
    rec = load_json(receipt_path(mod_id), {})
    deployed = []
    for f in rec.get("files", []):
        p = Path(f["path"])
        deployed.append({"file": p.name, "present": p.is_file(), "intact": p.is_file() and sha256_file(p) == f["sha256"]})
    groot, _ = find_game(game_arg)
    ld = loader(groot)
    pak = (m or {}).get("pak_name") or (Path(rec["files"][0]["path"]).stem.replace("_9999999_P", "") if rec.get("files") else None)
    logs = [scan_log(p, pak, errors()) for p in newest_logs(log_dir())]
    out = {"mod": mod_id, "deployed": deployed or "not deployed", "loader": ld, "logs": logs,
           "look_for": ["open the hero in the lobby with this skin equipped",
                        "the changed area shows the edit (compare build/preview/sheet.png)",
                        "play one match or practice range: no missing textures, no crash"]}
    if confirm:
        if not root:
            raise ForgeError("NO_PROJECT", "--confirm records into a project", "run inside the project or pass --project")
        if tier not in ("load", "gameplay"):
            raise ForgeError("BAD_TIER", "tier must be load or gameplay")
        m.setdefault("evidence", []).append({"tier": tier, "note": confirm, "version": m["version"],
                                             "date": time.strftime("%Y-%m-%d"), "observed_by": "owner"})
        P.save_manifest(root, m)
        out["recorded"] = {"tier": tier, "note": confirm}
    return out
