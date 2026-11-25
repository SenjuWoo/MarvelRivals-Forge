"""mrforge validate: rules over the built triple, reported per evidence tier.

Tiers: static (names/flags/paths), build (receipt), package (round trip out of the container).
load and gameplay need the game running and are always `not_run` here.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import index as I
from . import mat as M
from . import phys as PH
from . import project as P
from .build import triple
from .extract import load_lock
from .game import find_game, layout, version
from .mods import conflicts, parse_filters, parse_info, scan
from .sync import require_usmap
from .tools import run_tool
from .uat import extract_vanilla, parse_extract_texture, pattern_for
from .util import fwd, load_json, sha256_file

LEAK_CLASSES = ("skeleton", "physics")


def _r(rule, status, detail, tier):
    return {"rule": rule, "status": status, "detail": detail, "tier": tier}


def _rmse(a: Path, b: Path) -> float | None:
    try:
        from PIL import Image, ImageChops, ImageStat
        ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
        if ia.size != ib.size:
            ib = ib.resize(ia.size)
        st = ImageStat.Stat(ImageChops.difference(ia, ib))
        return round(sum(x * x for x in st.rms) ** 0.5 / (255 * 3 ** 0.5) * 100, 3)
    except Exception:
        return None


def run(root: Path, game_arg=None, deep: bool = True) -> tuple[dict, bool]:
    root = Path(root)
    m = P.manifest(root)
    receipt = load_json(root / "dist" / "receipt.json", {})
    mesh_route = receipt.get("route") == "mesh" or "mesh" in receipt.get("routes", [])
    lk = load_lock(root, required=not mesh_route)  # mesh projects have no texture/material extraction
    lk.setdefault("changelist", receipt.get("changelist") or m.get("game_changelist"))
    res: list[dict] = []
    tr = triple(root, m)
    missing = [p.name for p in tr.values() if not p.is_file()]
    res.append(_r("V-NAME", "fail" if missing else "pass",
                  f"missing {missing}" if missing else f"{m['pak_name']}_9999999_P.{{pak,utoc,ucas}}", "static"))
    if missing:
        return _summary(res), False
    utoc = tr[".utoc"]
    info = run_tool("retoc-rivals-cli", ["info", fwd(utoc)], timeout=120)
    pi = parse_info(info["stdout"] + info["stderr"])
    enc = "Encrypted" in pi.get("flags", [])
    res.append(_r("V-FLAGS", "fail" if (enc or info["rc"] != 0) else "pass",
                  f"flags {pi.get('flags')}" + (" (encrypted: the game reports encrypted mods)" if enc else ""), "static"))
    man = run_tool("retoc-rivals-cli", ["manifest", "--filters", fwd(utoc)], timeout=300)
    pkgs = parse_filters(man["stdout"])
    groot, _ = find_game(game_arg)
    cl = version(groot)["changelist"]
    idx = I.load(lk["changelist"])
    adds = {I.norm_pkg(a).lower() for a in m.get("adds", [])}
    unknown = [p for p in pkgs if not I.exists(idx, p) and p.lower() not in adds]
    res.append(_r("V-PATHS", "fail" if (unknown or not pkgs) else "pass",
                  (f"not in vanilla build {lk['changelist']}: {unknown[:10]}" if unknown else
                   f"{len(pkgs)} packages, all vanilla paths") if pkgs else "container lists no packages", "static"))
    # Deliberate edits of the skin's post-process AnimBlueprint (physics route) are not placeholder leaks.
    allow = {I.norm_pkg(a).lower() for a in m.get("allow", []) + receipt.get("physics_edits", [])}
    leaks = [p for p in pkgs if (I.classify(p) in LEAK_CLASSES or "placeholder" in p.lower()) and p.lower() not in allow]
    res.append(_r("V-LEAK", "fail" if leaks else "pass",
                  f"skeleton/physics/placeholder packages packed: {leaks}" if leaks else "no skeleton, physics or placeholder packages",
                  "static"))
    stale = receipt.get("changelist") != cl
    res.append(_r("V-STALE", "fail" if stale else "pass",
                  f"built for {receipt.get('changelist')}, game is {cl}" if stale else f"built for installed build {cl}", "build"))
    out_ok = receipt and all(receipt.get("outputs", {}).get(p.name) == sha256_file(p) for p in tr.values())
    res.append(_r("V-RECEIPT", "pass" if out_ok else "fail",
                  "receipt matches the built files" if out_ok else "dist files differ from receipt.json (rebuild)", "build"))
    if deep:
        res += _roundtrip(root, m, lk, pkgs, groot)
        if mesh_route:
            res.append(_mesh_rule(root, groot, utoc, receipt, lk["changelist"]))
    try:
        # The forge's own deploy folders are excluded: redeploying a project is not a conflict.
        mods = [x for x in scan(layout(groot)["mods_dir"]) if "-mrforge-" not in x["folder"]]
        cf = conflicts(mods, pkgs)
        res.append(_r("V-CONFLICT", "warn" if cf else "pass",
                      f"deployed mods also provide: {cf[:5]}" if cf else "no deployed mod touches these packages", "static"))
    except Exception as e:  # conflict scan is advisory
        res.append(_r("V-CONFLICT", "skip", f"mods scan failed: {e}", "static"))
    ok = not any(r["status"] == "fail" for r in res)
    return _summary(res), ok


def _roundtrip(root: Path, m: dict, lk: dict, pkgs: list[str], groot: Path) -> list[dict]:
    out = []
    usmap = require_usmap(lk["changelist"])
    tex = {n: t for n, t in lk["textures"].items() if t["package"] in pkgs}
    mats = {k: r for k, r in lk["materials"].items() if r["package"] in pkgs}
    phys = {k: r for k, r in lk.get("physics", {}).items() if r["package"] in pkgs}
    if not tex and not mats and not phys:
        return out
    tmp = Path(tempfile.mkdtemp(prefix="mrf-validate-"))
    try:
        patterns = [pattern_for(x["package"]) for x in (*tex.values(), *mats.values(), *phys.values())]
        extract_vanilla(layout(groot)["paks_dir"], tmp / "raw", patterns, mod=str(triple(root, m)[".utoc"]))
        problems, warns, details = [], [], []
        for n, t in tex.items():
            ua = tmp / "raw" / t["package"]
            png = tmp / "png" / f"{n}.png"
            if not ua.is_file():
                problems.append(f"{n}: not extractable from the mod")
                continue
            r = run_tool("uassettool", ["extract_texture", fwd(ua), fwd(png), "--usmap", fwd(usmap)], timeout=600)
            info = parse_extract_texture(r["stdout"] + r["stderr"])
            if not info.get("ok"):
                problems.append(f"{n}: extract_texture failed")
                continue
            if info.get("format") != t.get("format"):
                problems.append(f"{n}: pixel format {info.get('format')} != vanilla {t.get('format')}")
            if not info.get("mips") or (t.get("mips") and info["mips"] < 2 <= t["mips"]):
                problems.append(f"{n}: mips {info.get('mips')} (vanilla {t.get('mips')})")
            if (info.get("width"), info.get("height")) != (t.get("width"), t.get("height")):
                warns.append(f"{n}: size {info.get('width')}x{info.get('height')} differs from vanilla {t.get('width')}x{t.get('height')}")
            details.append({"texture": n, "format": info.get("format"), "mips": info.get("mips"),
                            "size": f"{info.get('width')}x{info.get('height')}",
                            "rmse_vs_edit_pct": _rmse(root / t["work_png"], png)})
        if tex:
            st = "fail" if problems else ("warn" if warns else "pass")
            out.append({**_r("V-TEX", st, "; ".join(problems + warns) or f"{len(tex)} textures round-trip with vanilla format and mips",
                             "package"), "textures": details})
        mprob = []
        for k, rec in mats.items():
            ua = tmp / "raw" / rec["package"]
            jd = tmp / "json"
            jd.mkdir(exist_ok=True)
            r = run_tool("uassettool", ["to_json", fwd(ua), fwd(usmap), fwd(jd)], timeout=600)
            j = jd / (Path(rec["package"]).stem + ".json")
            if r["rc"] != 0 or not j.is_file():
                mprob.append(f"{k}: not readable from the mod")
                continue
            got = {p["name"]: p["value"] for p in M.params(load_json(j))}
            want = M.load_ops(root)["materials"].get(k, {})
            for param, val in want.items():
                g = got.get(param)
                if isinstance(val, list):
                    same = isinstance(g, list) and all(abs(a - b) < 1e-4 for a, b in zip(g, val))
                else:
                    same = g is not None and abs(g - float(val)) < 1e-4
                if not same:
                    mprob.append(f"{k}.{param}: {g} != {val}")
            j.unlink(missing_ok=True)
        if mats:
            out.append(_r("V-MAT", "fail" if mprob else "pass",
                          "; ".join(mprob) or f"{len(mats)} materials read back from the mod with the edited values", "package"))
        pprob, pdetail = [], []
        all_ops = PH.load_ops(root)["assets"]
        for k, rec in phys.items():
            ua = tmp / "raw" / rec["package"]
            jd = tmp / "pjson"
            jd.mkdir(exist_ok=True)
            r = run_tool("uassettool", ["to_json", fwd(ua), fwd(usmap), fwd(jd)], timeout=600)
            j = jd / (Path(rec["package"]).stem + ".json")
            if r["rc"] != 0 or not j.is_file():
                pprob.append(f"{k}: not readable from the mod")
                continue
            try:
                d = load_json(j)
                probs = PH.verify(d, all_ops.get(k, []))
                info = PH.listing(d)
            except Exception as e:  # an unparsed export is a failure, not a crash
                probs, info = [f"{getattr(e, 'message', e)}"], {"chains": [], "kawaii_nodes": 0}
            pprob += [f"{k}: {p}" for p in probs]
            pdetail.append({"asset": k, "kawaii_nodes": info["kawaii_nodes"], "chains": len(info["chains"]),
                            "ops": len(all_ops.get(k, []))})
        if phys:
            out.append({**_r("V-PHYS", "fail" if pprob else "pass",
                             "; ".join(pprob[:8]) or f"{len(phys)} physics assets read back from the mod with every edit "
                             "(chains, roots, parameters)", "package"), "physics": pdetail})
    except Exception as e:
        out.append(_r("V-ROUNDTRIP", "fail", f"round trip failed: {getattr(e, 'message', e)}", "package"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def _mesh_rule(root: Path, groot: Path, utoc: Path, receipt: dict, changelist: int) -> dict:
    """V-MESH: every packed mesh parses with the game's mappings; bones, slot names/order and tags equal vanilla;
    the lobby mesh is paired with the in-match mesh."""
    from .uebuild import verify_against_vanilla
    usmap = require_usmap(changelist)
    problems, warns, details = [], [], {}
    pkgs = receipt.get("mesh_packages", receipt.get("staged_packages", []))
    for pkg in pkgs:
        van = root / "vanilla" / "raw" / pkg
        if not van.is_file():
            problems.append(f"{pkg}: vanilla copy missing (rebuild)")
            continue
        c = verify_against_vanilla(root, groot, utoc, pkg, van, usmap)
        details[pkg] = c
        problems += [f"{Path(pkg).stem}: {p}" for p in c["problems"]]
    if pkgs and not any(p.endswith("_Lobby.uasset") for p in pkgs):
        warns.append("lobby mesh not built: hero select shows the vanilla model")
    st = "fail" if problems else ("warn" if warns else "pass")
    return {**_r("V-MESH", st, "; ".join(problems + warns) or f"{len(pkgs)} meshes match vanilla bones, slots and tags",
                 "package"), "meshes": details}


def _summary(res: list[dict]) -> dict:
    tiers = {}
    for tier in ("static", "build", "package"):
        rs = [r for r in res if r["tier"] == tier]
        tiers[tier] = ("fail" if any(r["status"] == "fail" for r in rs) else "pass") if rs else "not_run"
    tiers["load"] = "not_run"
    tiers["gameplay"] = "not_run"
    return {"tiers": tiers, "rules": res}
