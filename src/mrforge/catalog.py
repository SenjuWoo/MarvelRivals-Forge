"""Hero and skin names: vendored snapshot (knowledge/skins.json) plus an optional override layer.

The installed-truth index decides what exists in this build; this table only supplies names.
"""
from __future__ import annotations

import json
import time

from .home import home
from .util import ForgeError, KNOWLEDGE_DIR, load_json, save_json

UPSTREAM = "https://raw.githubusercontent.com/natimerry/repak-rivals/master/repak-gui/src/data/character_data.json"


def convert(rows: list[dict]) -> list[dict]:
    """Upstream rows (name, id, skinid, skin_name) -> {skin_id, hero_id, hero, skin}."""
    out, seen = [], set()
    for r in rows:
        sid = str(r.get("skinid", "")).strip()
        if not (sid.isdigit() and len(sid) == 7) or sid in seen:
            continue
        seen.add(sid)
        out.append({"skin_id": sid, "hero_id": sid[:4], "hero": r.get("name", "").strip(),
                    "skin": r.get("skin_name", "").strip()})
    return sorted(out, key=lambda x: x["skin_id"])


def rows() -> list[dict]:
    base = load_json(KNOWLEDGE_DIR / "skins.json")["skins"]
    over = load_json(home() / "cache" / "skins_override.json", {}).get("skins", [])
    if not over:
        return base
    merged = {r["skin_id"]: r for r in base}
    merged.update({r["skin_id"]: r for r in over})
    return sorted(merged.values(), key=lambda x: x["skin_id"])


def heroes() -> list[dict]:
    h: dict[str, dict] = {}
    for r in rows():
        e = h.setdefault(r["hero_id"], {"hero_id": r["hero_id"], "hero": r["hero"], "skins": 0})
        e["skins"] += 1
    return sorted(h.values(), key=lambda x: x["hero_id"])


def _match(text: str, *fields: str) -> bool:
    t = text.lower()
    return any(t in (f or "").lower() for f in fields)


def find_hero(text: str) -> list[dict]:
    return [h for h in heroes() if h["hero_id"] == text or _match(text, h["hero"])]


def skins_of(hero: str) -> list[dict]:
    hs = find_hero(hero)
    if not hs:
        raise ForgeError("HERO_NOT_FOUND", f"no hero matches {hero!r}", "mrforge hero list")
    ids = {h["hero_id"] for h in hs}
    return [r for r in rows() if r["hero_id"] in ids]


def find_skin(text: str) -> list[dict]:
    return [r for r in rows() if r["skin_id"] == text or _match(text, r["skin"], r["hero"] + " " + r["skin"])]


def resolve_skin(text: str) -> dict:
    """One skin from an id or a name. A 7-digit id not in the table is accepted as-is (index decides)."""
    t = str(text).strip()
    exact = [r for r in rows() if r["skin_id"] == t]
    if exact:
        return exact[0]
    if t.isdigit() and len(t) == 7:
        return {"skin_id": t, "hero_id": t[:4], "hero": "", "skin": "", "note": "not in the name table"}
    hits = [r for r in rows() if r["skin"].lower() == t.lower()] or find_skin(t)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ForgeError("SKIN_NOT_FOUND", f"no skin matches {text!r}", "mrforge skin find <text>")
    raise ForgeError("SKIN_AMBIGUOUS", f"{len(hits)} skins match {text!r}: " +
                     ", ".join(f"{h['skin_id']} {h['hero']} - {h['skin']}" for h in hits[:8]),
                     "pass the 7-digit skin id")


def sync(fetch=None) -> dict:
    from .sync import default_fetch
    raw = (fetch or default_fetch)(UPSTREAM)
    conv = convert(json.loads(raw))
    if not conv:
        raise ForgeError("CATALOG_EMPTY", "upstream table had no usable rows")
    save_json(home() / "cache" / "skins_override.json",
              {"source": UPSTREAM, "fetched": time.strftime("%Y-%m-%d"), "skins": conv})
    return {"rows": len(conv), "stored": "override layer in .mrforge/cache/skins_override.json"}
