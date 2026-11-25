"""Knowledge data (facts, routes, error signatures, docs) and the request router behind `mrforge plan`."""
from __future__ import annotations

import re

from .util import ForgeError, KNOWLEDGE_DIR, load_json


def facts(grep: str | None = None) -> list[dict]:
    fs = load_json(KNOWLEDGE_DIR / "facts.json")["facts"]
    if grep:
        g = grep.lower()
        fs = [f for f in fs if g in f["statement"].lower() or g in f["id"].lower()]
    return fs


def routes() -> list[dict]:
    return load_json(KNOWLEDGE_DIR / "routes.json")["routes"]


def errors() -> list[dict]:
    return load_json(KNOWLEDGE_DIR / "errors.json")["signatures"]


def docs() -> list[str]:
    return sorted(p.stem for p in KNOWLEDGE_DIR.glob("*.md"))


def doc(name: str) -> str:
    p = KNOWLEDGE_DIR / f"{name}.md"
    if not p.is_file():
        raise ForgeError("DOC_NOT_FOUND", f"no knowledge doc {name!r}", "mrforge knowledge  (lists the docs)")
    return p.read_text(encoding="utf-8")


def _score(request: str, route: dict) -> int:
    text = request.lower()
    score = 0
    for kw in route.get("keywords", []):
        if re.search(r"(?<![a-z])" + re.escape(kw.lower()) + r"(?![a-z])", text):
            score += 3 if " " in kw else 2
    for kw in route.get("weak_keywords", []):
        if kw.lower() in text:
            score += 1
    return score


KINDS_ROUTES = ("texture", "material", "mesh", "physics")


def plan(request: str, route_status: dict | None = None) -> dict:
    rs = routes()
    scored = sorted(((_score(request, r), i, r) for i, r in enumerate(rs)), key=lambda x: (-x[0], x[1]))
    best_score, _, best = scored[0]
    if best_score == 0:
        best = next(r for r in rs if r["id"] == "texture")
    alts = [r["id"] for s, _, r in scored[1:3] if s > 0]
    out = {"request": request, "route": best["id"], "summary": best["summary"], "release": best.get("release"),
           "commands": best["commands"], "docs": best.get("docs", []), "avoid": best.get("avoid", []),
           "confidence": "matched" if best_score else "default (no keyword matched; texture is the usual skin route)",
           "alternatives": alts}
    # Requests that name two editable routes ("bigger chest and jiggle") are one project with both kinds.
    strong = [r["id"] for sc, _, r in scored[1:] if sc >= 2 and r["id"] in KINDS_ROUTES and best["id"] in KINDS_ROUTES]
    if strong:
        out["combine"] = {"routes": [best["id"], *strong],
                          "how": f"one project: mrforge new \"<Mod Name>\" --skin <skinId> --kind {','.join([best['id'], *strong])}; "
                                 "do each route's edit steps, then one mrforge build"}
    if route_status is not None:
        out["availability"] = route_status.get(best.get("doctor_route", best["id"]), "unknown")
    return out
