"""mrforge selftest texture: the real-toolchain smoke run. Temp project -> extract -> hue -> build -> validate -> package.

Never deploys. Leaves nothing behind unless --keep.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from . import build, extract, package, project, tex, validate
from .catalog import resolve_skin
from .game import find_game, version
from .util import ForgeError

DEFAULT_SKIN = "1061303"


def mesh(skin: str = DEFAULT_SKIN, keep: bool = False, game_arg=None, lobby: bool = False) -> tuple[dict, bool]:
    """Unmodified round trip through the whole mesh route: export -> blend -> check -> UE build -> validate."""
    from . import mesh as X
    from .uebuild import build as ue_build
    t0 = time.time()
    steps = []
    tmp = Path(tempfile.mkdtemp(prefix="mrf-selftest-mesh-"))
    root = None
    try:
        s = resolve_skin(skin)
        groot, _ = find_game(game_arg)
        cl = version(groot)["changelist"]
        root = project.new("Selftest Mesh", s, ["mesh"], cl, out=str(tmp / "selftest-mesh"))
        r = X.export(root, lobby, game_arg)
        steps.append({"step": "mesh export", "ok": True, "seconds": r["seconds"]})
        X.blend(root)
        steps.append({"step": "mesh blend", "ok": True})
        c, cok = X.check(root)
        steps.append({"step": "mesh check", "ok": cok, "checks": c["checks"]})
        b = ue_build(root, game_arg)
        bok = all(v["ok"] for v in b["mesh_checks"].values())
        steps.append({"step": "mesh build", "ok": bok, "seconds": b["seconds"], "checks": b["mesh_checks"]})
        v, vok = validate.run(root, game_arg)
        steps.append({"step": "validate", "ok": vok, "tiers": v["tiers"]})
        p = package.run(root)
        steps.append({"step": "package", "ok": True, "sha256": p["sha256"]})
        ok = cok and bok and vok
        return {"skin": s["skin_id"], "changelist": cl, "tiers": v["tiers"], "rules": v["rules"], "steps": steps,
                "seconds": round(time.time() - t0, 1), "project": str(root) if keep else "(removed)"}, ok
    except ForgeError as e:
        steps.append({"step": "error", "ok": False, **e.as_dict()})
        return {"steps": steps, "seconds": round(time.time() - t0, 1)}, False
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


DEFAULT_TEXTURE = "T_{skin}_Body_01_D"


def texture(skin: str = DEFAULT_SKIN, texture_name: str | None = None, keep: bool = False, game_arg=None) -> tuple[dict, bool]:
    t0 = time.time()
    steps = []
    tmp = Path(tempfile.mkdtemp(prefix="mrf-selftest-"))
    root = None
    ok = False
    try:
        s = resolve_skin(skin)
        groot, _ = find_game(game_arg)
        cl = version(groot)["changelist"]
        root = project.new("Selftest Texture", s, ["texture"], cl, out=str(tmp / "selftest-texture"))
        steps.append({"step": "new", "ok": True})
        name = texture_name or DEFAULT_TEXTURE.format(skin=s["skin_id"])
        r = extract.run(root, textures=[name], game_arg=game_arg)
        steps.append({"step": "extract", "ok": True, "seconds": r["seconds"]})
        lk = extract.load_lock(root)
        if name not in lk["textures"]:
            raise ForgeError("SELFTEST_TEXTURE_MISSING", f"{name} was not extracted", "pass --texture <name>")
        tex.add_op(root, lk, name, {"op": "hue", "shift": 120.0})
        steps.append({"step": "tex hue 120", "ok": True})
        tex.sheet(root, lk, [name])
        steps.append({"step": "tex sheet", "ok": True})
        b = build.run(root)
        steps.append({"step": "build", "ok": True, "packages": b["packages"], "seconds": b["seconds"]})
        v, vok = validate.run(root, game_arg)
        steps.append({"step": "validate", "ok": vok, "tiers": v["tiers"],
                      "failed": [x for x in v["rules"] if x["status"] == "fail"]})
        p = package.run(root)
        steps.append({"step": "package", "ok": True, "sha256": p["sha256"]})
        ok = vok
        return {"skin": s["skin_id"], "texture": name, "changelist": cl, "tiers": v["tiers"], "rules": v["rules"],
                "steps": steps, "seconds": round(time.time() - t0, 1),
                "project": str(root) if keep else "(removed)"}, ok
    except ForgeError as e:
        steps.append({"step": "error", "ok": False, **e.as_dict()})
        return {"steps": steps, "seconds": round(time.time() - t0, 1), "project": str(root) if keep and root else "(removed)"}, False
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
