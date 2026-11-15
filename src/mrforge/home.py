"""Forge home: tools, caches, keys, receipts, logs and config. Never inside the game folder."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .util import load_json, save_json

SUBDIRS = ("tools", "cache/usmap", "cache/index", "cache/vanilla", "logs", "receipts")
DEFAULT_CONFIG = {"game": None, "projects_root": None, "deploy_prefix": "ZZZ"}


def forge_root() -> Path:
    """Repository root (src/mrforge -> src -> root). MRFORGE_ROOT overrides for unusual installs."""
    env = os.environ.get("MRFORGE_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def home(create: bool = True) -> Path:
    env = os.environ.get("MRFORGE_HOME")
    h = Path(env) if env else forge_root() / ".mrforge"
    if create:
        for s in SUBDIRS:
            (h / s).mkdir(parents=True, exist_ok=True)
    return h


def config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json(home() / "config.json", {}))
    return cfg


def save_config(updates: dict) -> dict:
    cfg = config()
    cfg.update(updates)
    save_json(home() / "config.json", cfg)
    return cfg


def projects_root() -> Path:
    p = config().get("projects_root")
    return Path(p) if p else forge_root() / "projects"


def log_line(kind: str, payload: dict) -> None:
    """Quiet diagnostic log: one JSON line per event, rotated at 2 MB."""
    try:
        log = home() / "logs" / "mrforge.log"
        if log.is_file() and log.stat().st_size > 2_000_000:
            os.replace(log, log.with_name("mrforge.1.log"))
        from .util import redact
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **payload}
        with open(log, "a", encoding="utf-8") as f:
            f.write(redact(json.dumps(rec, ensure_ascii=False, default=str)) + "\n")
    except OSError:
        pass
