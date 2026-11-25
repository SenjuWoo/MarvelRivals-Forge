"""mrforge command line.

Every command prints one JSON object: {ok, command, version, data, errors[], warnings[], gaps[]}.
Exit codes: 0 ok, 1 failure, 2 usage, 3 environment (game/tool/mapping missing).
Global options (anywhere on the line): --game <dir>, --project <dir>, --pretty.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from . import __version__
from .util import ForgeError, UsageError, redact


class Out:
    def __init__(self):
        self.warnings: list[str] = []
        self.gaps: list[str] = []
        self.errors: list[dict] = []

    def warn(self, w):
        if isinstance(w, list):
            self.warnings += [str(x) for x in w]
        elif w:
            self.warnings.append(str(w))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message, f"mrforge {self.prog.split(' ', 1)[-1] if ' ' in self.prog else ''} --help".strip())


GLOBAL = {"--game": True, "--project": True, "--pretty": False}


def split_globals(argv: list[str]) -> tuple[list[str], dict]:
    g = {"game": None, "project": None, "pretty": False}
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        key = a.split("=", 1)[0]
        if key in GLOBAL:
            name = key[2:]
            if GLOBAL[key]:
                if "=" in a:
                    g[name] = a.split("=", 1)[1]
                elif i + 1 < len(argv):
                    g[name] = argv[i + 1]
                    i += 1
                else:
                    raise UsageError(f"{key} needs a value")
            else:
                g[name] = True
        else:
            rest.append(a)
        i += 1
    return rest, g


# --- helpers ----------------------------------------------------------------

def _game_info(args):
    from .game import find_game, layout, version
    root, src = find_game(args.game)
    return root, layout(root), version(root)


def _project(args) -> Path:
    from .project import find
    return find(args.project)


def _lock(root):
    from .extract import load_lock
    return load_lock(root)


# --- commands ---------------------------------------------------------------

def cmd_version(args, out):
    return {"version": __version__}


def cmd_game(args, out):
    from .game import info
    d = info(args.game)
    if not d["loader"]["present"]:
        out.warn("ASI loader or UTOC signature bypass missing: mods will not load")
    if d["running"]:
        out.warn("the game is running")
    return d


def cmd_setup(args, out):
    from .home import save_config
    from .tools import setup
    if args.game:
        save_config({"game": args.game})
    if args.ue:
        from .ue import build_version
        if build_version(Path(args.ue)) != (5, 3, 2):
            raise UsageError(f"{args.ue} is not an Unreal Engine 5.3.2 folder (Engine/Build/Build.version)")
        save_config({"ue_root": args.ue})
    if args.projects_root:
        save_config({"projects_root": args.projects_root})
    d = setup(args.from_dirs, args.offline, args.force, args.only)
    for e in d["errors"]:
        out.errors.append(e)
    if d["oodle"] and not d["oodle"]["present"]:
        out.warn("Oodle DLL not present yet: the first extraction downloads it (needs network)")
    return d


def cmd_sync(args, out):
    from .sync import sync
    _, _, ver = _game_info(args)
    d = sync(ver["changelist"], offline=args.offline, allow_nearest=args.allow_nearest)
    if not d.get("exact", True):
        out.warn(f"using mapping for build {d.get('build')} instead of {ver['changelist']}: property reads may be wrong")
    if d.get("warning"):
        out.warn(d["warning"])
    return d


def cmd_doctor(args, out):
    from .doctor import run_doctor
    d, ok = run_doctor(args.game)
    for s in ("payload", "toolchain", "game"):
        for c in d["sections"][s]:
            if c["status"] == "fail":
                out.errors.append({"code": "DOCTOR_" + c["id"].upper(), "message": c["detail"], "fix": c["fix"]})
    for r in d["routes"]:
        if r["status"] != "available":
            out.gaps.append(f"route {r['route']}: {r['status']} (needs {r['needs']})")
    return d


def _walk(p: argparse.ArgumentParser, prefix: str) -> list[dict]:
    out = []
    for action in p._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                full = f"{prefix} {name}".strip()
                kids = _walk(sub, full)
                if kids:
                    out += kids
                else:
                    opts = []
                    for a in sub._actions:
                        if a.dest == "help":
                            continue
                        opts.append({"name": a.option_strings[0] if a.option_strings else a.dest,
                                     "required": bool(a.required) or not a.option_strings, "help": a.help or ""})
                    out.append({"command": full, "help": sub.description or "", "args": opts})
    return out


def cmd_capabilities(args, out):
    from .doctor import route_checks, toolchain_checks
    cmds = _walk(parser(), "")
    routes = None
    if not args.offline:
        try:
            _, tool_state = toolchain_checks()
            routes = {r["route"]: r["status"] for r in route_checks(tool_state, {"usmap": True})}
        except Exception as e:  # capability listing must work on a bare machine
            out.warn(f"route availability unknown: {e}")
    return {"forge": "MarvelRivals-Forge", "version": __version__, "commands": cmds, "routes": routes,
            "global": ["--game <folder>", "--project <folder>", "--pretty"],
            "exit_codes": {"0": "ok", "1": "failure", "2": "usage", "3": "environment"},
            "output": "{ok, command, version, data, errors[], warnings[], gaps[]}"}


def cmd_guide(args, out):
    from .knowledge import routes
    return {"cold_start": ["mrforge doctor", "mrforge setup --from <folder with tool copies>  (or plain mrforge setup)",
                           "mrforge sync", "mrforge index", "mrforge plan \"<what the user wants>\"",
                           "follow the commands it prints"],
            "routes": [{"id": r["id"], "summary": r["summary"], "release": r.get("release"), "commands": r["commands"]}
                       for r in routes()],
            "rules": ["vanilla comes from the game containers only (never from ~mods)",
                      "look at build/preview/sheet.png before building",
                      "load and gameplay are proven only by someone looking in game: mrforge check-load --confirm"]}


def cmd_knowledge(args, out):
    from .knowledge import doc, docs
    if args.topic:
        return {"topic": args.topic, "text": doc(args.topic)}
    return {"topics": docs(), "hint": "mrforge knowledge <topic>"}


def cmd_facts(args, out):
    from .knowledge import facts
    return {"facts": facts(args.grep)}


def cmd_plan(args, out):
    from .knowledge import plan
    status = None
    if not args.offline:
        try:
            from .doctor import route_checks, toolchain_checks
            _, ts = toolchain_checks()
            status = {r["route"]: r["status"] for r in route_checks(ts, {"usmap": True})}
        except Exception:
            status = None
    d = plan(" ".join(args.request), status)
    if d["route"] in ("physics", "unsupported"):
        out.gaps.append(d["summary"])
    elif d.get("release") not in ("v0.1", None) and d.get("availability") != "available":
        out.gaps.append(f"route {d['route']} ships in {d['release']}; availability: {d.get('availability')}")
    return d


def cmd_hero(args, out):
    from .catalog import find_hero, heroes
    if args.action == "list":
        return {"heroes": heroes()}
    if not args.text:
        raise UsageError("hero find needs text")
    return {"heroes": find_hero(" ".join(args.text))}


def cmd_skin(args, out):
    from .catalog import find_skin, skins_of
    text = " ".join(args.text) if args.text else ""
    if args.action == "list":
        if not text:
            raise UsageError("skin list needs a hero name or id", "mrforge skin list \"Storm\"")
        return {"skins": skins_of(text)}
    if args.action == "find":
        if not text:
            raise UsageError("skin find needs text")
        return {"skins": find_skin(text)}
    from .skin import inspect
    if not text:
        raise UsageError("skin inspect needs a skin id or name")
    d = inspect(text, args.quick, args.game, args.refresh)
    ov = d.get("overridden_by_mods")
    if isinstance(ov, dict) and ov and "skipped" not in ov:
        out.warn(f"{len(ov)} packages of this skin are overridden by deployed mods")
    if d.get("deep", {}).get("shared_from_other_skins"):
        out.warn("materials reference assets of other skin ids: editing those changes other skins too")
    return d


def cmd_catalog(args, out):
    from .catalog import sync
    return sync()


def cmd_index(args, out):
    from .index import build, index_path
    _, lay, ver = _game_info(args)
    idx = build(lay["paks_dir"], ver["changelist"])
    return {"changelist": idx["changelist"], "packages": len(idx["packages"]), "containers": len(idx["containers"]),
            "seconds": idx["seconds"], "stored": str(index_path(ver["changelist"]))}


def cmd_mods(args, out):
    from .mods import scan
    _, lay, _ = _game_info(args)
    mods = scan(lay["mods_dir"], use_cache=not args.refresh)
    bad = [m for m in mods if m.get("flags_bad")]
    if bad:
        out.warn(f"{len(bad)} encrypted/obfuscated/stripped mods (reported by the game since Season 11)")
    if not args.packages:
        mods = [{k: v for k, v in m.items() if k != "packages"} for m in mods]
    return {"mods_dir": str(lay["mods_dir"]), "count": len(mods), "mods": mods}


def cmd_conflicts(args, out):
    from .mods import conflicts, scan
    _, lay, _ = _game_info(args)
    mods = scan(lay["mods_dir"])
    if args.project or args.mine:
        root = _project(args)
        lk = _lock(root)
        pk = [x["package"] for sec in ("textures", "materials", "physics") for x in lk.get(sec, {}).values()]
        mods = [m for m in mods if "-mrforge-" not in m["folder"]]
        return {"project": str(root), "conflicts": conflicts(mods, pk)}
    return {"conflicts": conflicts(mods)}


def cmd_new(args, out):
    from .catalog import resolve_skin
    from .project import new
    s = resolve_skin(args.skin)
    cl = None
    try:
        _, _, ver = _game_info(args)
        cl = ver["changelist"]
    except ForgeError as e:
        out.warn(f"game not found ({e.code}); game_changelist will be set by mrforge extract")
    kinds = [k.strip() for k in args.kind.split(",") if k.strip()]
    root = new(args.name, s, kinds, cl, args.out, args.description or "")
    first = {"mesh": "mrforge mesh export --lobby", "physics": "mrforge extract --physics",
             "sound": "mrforge extract --sounds"}.get(
        kinds[0] if kinds else "", f"mrforge extract --textures \"T_{s['skin_id']}_*\"")
    return {"project": str(root), "skin": s, "next": f"cd \"{root}\" && {first}"}


def cmd_bump(args, out):
    from .project import bump
    return bump(_project(args), args.part, args.note or "")


def cmd_extract(args, out):
    from .extract import run
    sounds = args.sounds or args.bank
    if not (args.textures or args.materials or args.all or args.package or args.physics or sounds):
        raise UsageError("choose what to extract",
                         "--textures \"<glob>\" and/or --materials, --physics, --sounds, --all, --package <path>")
    root = _project(args)
    d = {}
    if args.textures or args.materials or args.all or args.package or args.physics:
        d = run(root, args.textures, args.materials, args.all, args.package, args.vfx, args.game, args.physics)
        out.warn(d.pop("warnings"))
    if sounds:
        from . import snd as SN
        from .project import manifest
        groot, _, ver = _game_info(args)
        s = SN.extract_banks(root, groot, ver["changelist"], manifest(root)["skin_id"], args.bank)
        out.warn(s.pop("warnings"))
        d["sounds"] = s["banks"]
        d.setdefault("next", "mrforge sound list, then mrforge sound replace <event> <file.wav|mp3|ogg>")
    return d


def cmd_sound(args, out):
    from . import snd as SN
    root = _project(args)
    a = args.action
    if a == "list":
        rows = SN.listing(root, args.event)
        return {"events": rows, "count": len(rows),
                "note": "left/right = primary/secondary fire, e/q/shift/f = abilities, display_* = hero select and MVP"}
    if a == "replace":
        if bool(args.event) == (args.media is not None):
            raise UsageError("give an event name or --media <id>", "mrforge sound list")
        d = SN.replace(root, args.event, Path(args.file), args.media, args.keep_layers, args.gain)
        if d["shared_with"]:
            out.warn(f"these events play the same media and change too: {d['shared_with'][:8]}")
        out.gaps.append("sound is proven only by hearing it in game (mrforge deploy, then check-load --confirm)")
        d["next"] = "mrforge build, then mrforge validate"
        return d
    if a == "reset":
        return {"reset": SN.reset(root, args.target)}
    raise UsageError(f"unknown sound action {a}")


def cmd_tex(args, out):
    from . import tex as X
    root = _project(args)
    lk = _lock(root)
    a = args.action
    if a == "list":
        return {"textures": X.listing(root, lk)}
    if a == "sheet":
        return X.sheet(root, lk, args.names or None)
    if a == "reset":
        return {"reset": X.reset(root, lk, args.texture)}
    if a == "hue":
        op = {"op": "hue", "shift": args.shift}
    elif a == "tint":
        op = {"op": "tint", "color": list(X.parse_color(args.color)), "strength": args.strength}
    elif a == "levels":
        op = {"op": "levels", "black": args.black, "white": args.white, "gamma": args.gamma}
    elif a == "overlay":
        op = {"op": "overlay", "opacity": args.opacity}
        if args.at:
            try:
                op["at"] = [int(v) for v in args.at.split(",")]
            except ValueError as e:
                raise UsageError("--at takes X,Y") from e
    elif a == "replace":
        op = {"op": "replace", "keep_size": args.keep_size}
    else:
        raise UsageError(f"unknown tex action {a}")
    d = X.add_op(root, lk, args.texture, op, getattr(args, "force", False), getattr(args, "mask", None),
                 getattr(args, "image", None))
    out.warn(d.pop("warnings"))
    if a == "replace" and not args.keep_size:
        out.gaps.append("replace resizes to the vanilla size; other sizes are unverified in game (assumption A5)")
    d["next"] = "mrforge tex sheet, look at build/preview/sheet.png, then mrforge build"
    return d


def cmd_mat(args, out):
    from . import mat as M
    from .util import load_json
    root = _project(args)
    lk = _lock(root)
    if args.action == "list":
        keys = M.resolve_keys(lk, args.material) if args.material else sorted(lk["materials"])
        ops = M.load_ops(root)["materials"]
        res = []
        for k in keys:
            d = load_json(root / lk["materials"][k]["work_json"])
            res.append({"material": k, "parent": M.parent(d), "params": M.params(d), "edits": ops.get(k, {})})
        return {"materials": res}
    if args.action == "set":
        return {"set": M.record(root, lk, args.material, args.param, args.value)}
    if args.action == "reset":
        ops = M.load_ops(root)
        keys = M.resolve_keys(lk, args.material)
        for k in keys:
            ops["materials"].pop(k, None)
        from .util import save_json
        save_json(M.ops_path(root), ops)
        return {"reset": keys}
    raise UsageError("unknown mat action")


def cmd_phys(args, out):
    from . import phys as PH
    from .util import load_json, save_json
    root = _project(args)
    lk = _lock(root)
    a = args.action
    if a == "presets":
        return {"chain_presets": PH.PRESETS, "chain_params": sorted(PH.PARAMS), "spring_presets": PH.SPRING_PRESETS}
    if a == "list":
        import fnmatch
        res = []
        for k in PH.resolve_keys(lk, args.asset) if args.asset else sorted(lk.get("physics", {})):
            info = PH.listing(PH.apply(root, lk, k))
            if args.bone:
                info["chains"] = [c for c in info["chains"] if any(fnmatch.fnmatchcase(r, args.bone) for r in c["roots"])]
            res.append({"asset": k, **info, "edits": PH.load_ops(root)["assets"].get(k, [])})
        if not res:
            raise ForgeError("PHYSICS_NOT_EXTRACTED", "no physics asset extracted", "mrforge extract --physics")
        return {"assets": res}
    if a == "reset":
        ops = PH.load_ops(root)
        keys = PH.resolve_keys(lk, args.asset) if args.asset else sorted(ops["assets"])
        for k in keys:
            ops["assets"].pop(k, None)
        save_json(PH.ops_path(root), ops)
        return {"reset": keys}
    if a == "add-chain":
        params = PH.parse_params(args.param, args.preset)
        done = []
        for bone in args.root:
            op = {"op": "add_chain", "root": bone, "params": params}
            if args.host:
                op["host"] = args.host
            done += PH.record(root, lk, args.asset, op)
        names = set()
        for k in {x["asset"] for x in done}:
            names |= set(load_json(root / lk["physics"][k]["vanilla_json"]).get("NameMap", []))
        unknown = [b for b in args.root if b not in names]
        if unknown:
            out.warn(f"{unknown} not referenced by the vanilla asset: check the exact bone name (mrforge mesh blend + "
                     "Blender, or FModel); a wrong name simulates nothing")
        out.gaps.append("physics runs in game only: jiggle is proven by an in-game look (check-load --confirm)")
        return {"added": done, "next": "mrforge build, then mrforge validate"}
    if a == "springs":
        params = PH.spring_params(args.preset, args.stiffness, args.damping, args.max_displacement, args.rotate)
        bones = PH.region_bones(args.region, args.bone)
        done = PH.record(root, lk, args.asset, {"op": "springs", "bones": bones, "params": params})
        out.gaps.append("springs are built in Unreal 5.3.2 at mrforge build (needs VS 2022 MSVC v143); the result is "
                        "proven only by an in-game look")
        return {"added": done, "note": "the asset is rebuilt from its vanilla graph plus these springs at build time",
                "next": "mrforge build, then mrforge validate"}
    if a == "set":
        if not (args.bone or args.node):
            raise UsageError("choose chains with --bone <glob> and/or --node <name>", "mrforge phys list shows them")
        value = args.value
        if args.param in PH.BOOL_PARAMS:
            value = str(value).lower() in ("1", "true", "yes", "on")
        else:
            try:
                value = float(value)
            except ValueError as e:
                raise UsageError(f"{value!r} is not a number") from e
        op = {"op": "set", "param": args.param, "value": value}
        for k in ("bone", "node", "chain"):
            if getattr(args, k) is not None:
                op[k] = getattr(args, k)
        return {"set": PH.record(root, lk, args.asset, op), "next": "mrforge build"}
    raise UsageError(f"unknown phys action {a}")


def cmd_mesh(args, out):
    from . import mesh as X
    root = _project(args)
    a = args.action
    if a == "export":
        d = X.export(root, args.lobby, args.game)
    elif a == "blend":
        d = X.blend(root, args.force)
    elif a == "fbx":
        d = X.fbx(root)
    elif a == "inflate":
        d = X.inflate(root, args.bone, args.factor, args.mesh, not args.no_children)
    elif a == "preview":
        d = X.preview(root, args.focus)
    elif a == "build":
        from .uebuild import build
        d = build(root, args.game)
        out.warn(d.pop("warnings"))
        d["next"] = "mrforge validate"
        for pkg, c in d["mesh_checks"].items():
            for prob in c["problems"]:
                out.errors.append({"code": "V-MESH", "message": f"{pkg}: {prob}"})
        out.gaps.append("load tier: mesh mods must be looked at in game (lobby and a match) before they count as working")
        return d
    elif a == "check":
        d, ok = X.check(root)
        for c in d["checks"]:
            for prob in c["problems"]:
                out.errors.append({"code": "MESH_CHECK", "message": f"{c['mesh']}: {prob}",
                                   "fix": "restore bone names/hierarchy and material slot names/order to vanilla"})
    else:
        raise UsageError(f"unknown mesh action {a}")
    return d


def cmd_build(args, out):
    from .build import run
    d = run(_project(args), args.game)
    out.warn(d.pop("warnings"))
    for pkg, c in d["mesh_checks"].items():
        for prob in c["problems"]:
            out.errors.append({"code": "V-MESH", "message": f"{pkg}: {prob}"})
    if "mesh" in d["routes"] or "physics" in d["routes"]:
        out.gaps.append("load tier: mesh and physics edits must be looked at in game before they count as working")
    d["next"] = "mrforge validate"
    return d


def cmd_validate(args, out):
    from .validate import run
    d, ok = run(_project(args), args.game, not args.quick)
    for r in d["rules"]:
        if r["status"] == "fail":
            out.errors.append({"code": r["rule"], "message": r["detail"]})
        elif r["status"] == "warn":
            out.warn(f"{r['rule']}: {r['detail']}")
    out.gaps.append("load and gameplay tiers need an in-game check (mrforge deploy, then mrforge check-load --confirm)")
    return d


def cmd_package(args, out):
    from .package import run
    return run(_project(args))


def cmd_deploy(args, out):
    from . import deploy as D
    if args.status:
        return D.status()
    d = D.deploy(_project(args), args.prefix, args.game)
    out.gaps.append("load tier: start the game and look at the skin, then mrforge check-load --confirm \"<what you saw>\"")
    return d


def cmd_undeploy(args, out):
    from . import deploy as D
    mod_id = args.id
    if not mod_id:
        from .project import manifest
        mod_id = manifest(_project(args))["id"]
    d = D.undeploy(mod_id)
    for k in d["kept"]:
        out.warn(f"kept {k['path']}: {k['reason']}")
    return d


def cmd_selftest(args, out):
    from .selftest import mesh, physics, texture
    if args.route == "mesh":
        d, ok = mesh(args.skin, args.keep, args.game, args.lobby)
    elif args.route == "physics":
        d, ok = physics(args.skin, args.keep, args.game)
    else:
        d, ok = texture(args.skin, args.texture, args.keep, args.game)
    for r in d.get("rules", []):
        if r["status"] == "warn":
            out.warn(f"{r['rule']}: {r['detail']}")
    if not ok:
        for s in d["steps"]:
            if not s.get("ok"):
                out.errors.append({"code": s.get("code", "SELFTEST_STEP_FAILED"), "message": s.get("message", s["step"]),
                                   "fix": s.get("fix", "")})
    out.gaps.append("selftest never deploys: load/gameplay not_run")
    return d


def cmd_checkload(args, out):
    from .checkload import run
    root = None
    try:
        root = _project(args)
    except ForgeError:
        if args.confirm:
            raise
    d = run(args.id, root, args.game, args.confirm, args.tier)
    if not args.confirm:
        out.gaps.append("load/gameplay are recorded only from your observation: mrforge check-load --confirm \"<note>\"")
    return d


# --- parser -----------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = Parser(prog="mrforge", description="MarvelRivals-Forge: make Marvel Rivals skin mods")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)

    def add(name, fn, help_):
        sp = sub.add_parser(name, description=help_, help=help_)
        sp.set_defaults(fn=fn, cmdname=name)
        return sp

    add("version", cmd_version, "print the forge version")
    add("game", cmd_game, "find the installed game; build, loader, mod manager")
    s = add("setup", cmd_setup, "fetch or adopt the pinned tools into .mrforge/tools")
    s.add_argument("--from", dest="from_dirs", action="append", help="folder with existing tool copies (matched by hash)")
    s.add_argument("--offline", action="store_true", help="never download")
    s.add_argument("--force", action="store_true", help="re-resolve even when installed")
    s.add_argument("--only", action="append", help="limit to one tool name (repeatable)")
    s.add_argument("--ue", help="Unreal Engine 5.3.2 folder to remember")
    s.add_argument("--projects-root", help="where mrforge new creates projects")
    s = add("sync", cmd_sync, "download the mapping (.usmap) for the installed build and the AES key")
    s.add_argument("--offline", action="store_true", help="use the cache only")
    s.add_argument("--allow-nearest", action="store_true", help="accept the nearest lower build's mapping")
    add("doctor", cmd_doctor, "check payload, tools, game, data and routes")
    s = add("capabilities", cmd_capabilities, "all commands (generated from the parser) and route availability")
    s.add_argument("--offline", action="store_true", help="skip tool probes")
    add("guide", cmd_guide, "cold-start runbook and routes")
    s = add("knowledge", cmd_knowledge, "list or read knowledge docs")
    s.add_argument("topic", nargs="?", help="doc name")
    s = add("facts", cmd_facts, "verified facts with tier and source")
    s.add_argument("--grep", help="filter text")
    s = add("plan", cmd_plan, "route a request to exact commands")
    s.add_argument("request", nargs="+", help="what the mod should do")
    s.add_argument("--offline", action="store_true", help="skip availability probes")

    s = add("hero", cmd_hero, "hero names and ids")
    s.add_argument("action", choices=["list", "find"])
    s.add_argument("text", nargs="*")
    s = add("skin", cmd_skin, "skin names, ids and contents")
    s.add_argument("action", choices=["list", "find", "inspect"])
    s.add_argument("text", nargs="*")
    s.add_argument("--quick", action="store_true", help="inspect: index only, no extraction")
    s.add_argument("--refresh", action="store_true", help="inspect: ignore the cached deep result")
    s = add("catalog", cmd_catalog, "refresh the skin name table from upstream into an override layer")
    s.add_argument("action", choices=["sync"])
    add("index", cmd_index, "build the vanilla package index for the installed build")
    s = add("mods", cmd_mods, "installed mods with flags (read-only)")
    s.add_argument("action", choices=["list"])
    s.add_argument("--packages", action="store_true", help="include package lists")
    s.add_argument("--refresh", action="store_true", help="ignore the scan cache")
    s = add("conflicts", cmd_conflicts, "packages provided by more than one mod (or by deployed mods and this project)")
    s.add_argument("--mine", action="store_true", help="compare the current project with deployed mods")

    s = add("new", cmd_new, "create a mod project")
    s.add_argument("name")
    s.add_argument("--skin", required=True, help="7-digit skin id or skin name")
    s.add_argument("--kind", default="texture", help="any of texture,material,mesh,physics,sound (comma-separated)")
    s.add_argument("--out", help="project folder (default <projects root>/<slug>)")
    s.add_argument("--description", help="text for README.txt in the package")
    s = add("bump", cmd_bump, "bump the project version and add a changelog entry")
    s.add_argument("part", nargs="?", default="patch", choices=["major", "minor", "patch"])
    s.add_argument("--note", help="changelog line")
    s = add("extract", cmd_extract, "extract vanilla textures/materials/physics assets of the project's skin")
    s.add_argument("--textures", action="append", help="glob over texture names, e.g. \"T_*_Body_*\" (repeatable)")
    s.add_argument("--materials", action="store_true", help="all material instances of the skin")
    s.add_argument("--all", action="store_true", help="all textures and materials of the skin")
    s.add_argument("--package", action="append", help="any vanilla package path, e.g. a shared texture (repeatable)")
    s.add_argument("--vfx", action="store_true", help="include VFX folders")
    s.add_argument("--physics", action="store_true",
                   help="the skin's post-process AnimBlueprints (Post_<skin>_Physics and _Lobby_Physics)")
    s.add_argument("--sounds", action="store_true",
                   help="the skin's sound banks (bnk_sfx_<skin>, bnk_display_<skin>) with their events")
    s.add_argument("--bank", action="append", help="another sound bank by name, e.g. bnk_vo_1061001 (repeatable)")

    s = add("tex", cmd_tex, "texture edits (recorded ops, re-applied on build)")
    ts = s.add_subparsers(dest="action", required=True, parser_class=Parser)
    ts.add_parser("list", description="extracted textures and their state")
    t = ts.add_parser("sheet", description="vanilla|edited comparison image in build/preview/sheet.png")
    t.add_argument("names", nargs="*")
    t = ts.add_parser("reset", description="drop ops and restore vanilla")
    t.add_argument("texture")

    def tex_common(t, colour=True):
        t.add_argument("texture", help="texture name or glob")
        t.add_argument("--mask", help="grayscale PNG: white = apply, black = keep vanilla")
        if colour:
            t.add_argument("--force", action="store_true", help="allow colour ops on normal maps")

    t = ts.add_parser("hue", description="rotate hue")
    tex_common(t)
    t.add_argument("--shift", type=float, required=True, help="degrees")
    t = ts.add_parser("tint", description="blend toward a colour (keeps shading)")
    tex_common(t)
    t.add_argument("--color", required=True, help="#rrggbb or r,g,b")
    t.add_argument("--strength", type=float, default=0.6, help="0..1")
    t = ts.add_parser("levels", description="black/white point and gamma")
    tex_common(t)
    t.add_argument("--black", type=int, default=0)
    t.add_argument("--white", type=int, default=255)
    t.add_argument("--gamma", type=float, default=1.0)
    t = ts.add_parser("overlay", description="composite a PNG (logo, decal, pattern) over the texture")
    tex_common(t, colour=False)
    t.add_argument("image", help="PNG with alpha")
    t.add_argument("--opacity", type=float, default=1.0)
    t.add_argument("--at", help="X,Y to place at native size (default: stretch to the texture)")
    t = ts.add_parser("replace", description="use your own PNG (captures hand paint)")
    tex_common(t, colour=False)
    t.add_argument("image", help="PNG")
    t.add_argument("--keep-size", action="store_true", help="do not resize to the vanilla size")
    for name, sp in ts.choices.items():
        sp.set_defaults(fn=cmd_tex, cmdname=f"tex {name}")

    s = add("mat", cmd_mat, "material instance parameters")
    ms = s.add_subparsers(dest="action", required=True, parser_class=Parser)
    t = ms.add_parser("list", description="parameters each extracted material overrides")
    t.add_argument("material", nargs="?")
    t = ms.add_parser("set", description="set a scalar or vector parameter (applies to game and Lobby copies with a bare name)")
    t.add_argument("material")
    t.add_argument("param")
    t.add_argument("value")
    t = ms.add_parser("reset", description="drop edits for a material")
    t.add_argument("material")
    for name, sp in ms.choices.items():
        sp.set_defaults(fn=cmd_mat, cmdname=f"mat {name}")

    s = add("sound", cmd_sound, "sound route: replace the skin's sounds with your own audio (no Wwise needed)")
    ss = s.add_subparsers(dest="action", required=True, parser_class=Parser)
    t = ss.add_parser("list", description="events of the extracted banks with their media (variations, layers)")
    t.add_argument("event", nargs="?", help="glob over event names, e.g. \"*left*\"")
    t = ss.add_parser("replace", description="replace an event's sound (every variation) with any audio file ffmpeg reads")
    t.add_argument("event", nargs="?", help="event name from sound list, e.g. sfx_1061303_left_release2_play")
    t.add_argument("file", help="audio file (.wav, .mp3, .ogg, .flac, ...), cut at 30 s")
    t.add_argument("--media", type=int, help="replace one media id instead of an event")
    t.add_argument("--keep-layers", action="store_true",
                   help="keep the event's other layers (default: they get 10 ms of silence so your sound plays once)")
    t.add_argument("--gain", type=float, default=0.0, help="volume change in dB")
    t = ss.add_parser("reset", description="drop sound replacements")
    t.add_argument("target", nargs="?", help="event name or media id (default: all)")
    for name, sp in ss.choices.items():
        sp.set_defaults(fn=cmd_sound, cmdname=f"sound {name}")

    s = add("phys", cmd_phys, "physics route: KawaiiPhysics chains (jiggle, hair, cloth) in the skin's post-process AnimBlueprint")
    ps = s.add_subparsers(dest="action", required=True, parser_class=Parser)
    t = ps.add_parser("list", description="chains per KawaiiPhysics node (evaluation order), roots and parameters")
    t.add_argument("asset", nargs="?", help="Post_<skin>_Physics (default: every extracted asset)")
    t.add_argument("--bone", help="only chains whose root matches this glob")
    ps.add_parser("presets", description="parameter presets for add-chain (jiggle, bouncy, firm)")
    t = ps.add_parser("add-chain", description="simulate a bone chain that has no physics yet (e.g. chest or butt jiggle)")
    t.add_argument("--root", action="append", required=True, help="root bone; its children swing (repeatable)")
    t.add_argument("--preset", choices=["jiggle", "bouncy", "firm"], default="jiggle")
    t.add_argument("--param", action="append", help="Param=value override, e.g. Damping=0.2 (repeatable)")
    t.add_argument("--host", help="KawaiiPhysics node to add the chain to (default: the node evaluated last)")
    t.add_argument("--asset", help="physics asset (default: every extracted asset with KawaiiPhysics nodes)")
    t = ps.add_parser("set", description="change a parameter on existing chains (e.g. softer hair, stiffer skirt)")
    t.add_argument("param")
    t.add_argument("value")
    t.add_argument("--bone", help="chains whose root matches this glob, e.g. *hair*")
    t.add_argument("--node", help="one KawaiiPhysics node by name")
    t.add_argument("--chain", type=int, help="chain index inside the node")
    t.add_argument("--asset", help="physics asset (default: every extracted asset with KawaiiPhysics nodes)")
    t = ps.add_parser("springs", description="spring-bone jiggle rebuilt in Unreal (hero select / lobby: no KawaiiPhysics node there)")
    t.add_argument("--region", action="append",
                   help="body region: chest, butt, thighs (repeatable; expands to the rig's soft-tissue bones)")
    t.add_argument("--bone", action="append", help="bone that jiggles, e.g. L_Breast_01_Jnt (repeatable)")
    t.add_argument("--preset", choices=["reference", "soft", "firm"], default="reference")
    t.add_argument("--stiffness", type=float, help="spring stiffness (reference 80)")
    t.add_argument("--damping", type=float, help="spring damping (reference 6)")
    t.add_argument("--max-displacement", type=float, help="cm the bone may move (reference 3)")
    t.add_argument("--rotate", action="store_true", help="also spring the rotation (default: translation only)")
    t.add_argument("--asset", help="post-process asset (default: Post_<skin>_Lobby_Physics)")
    t = ps.add_parser("reset", description="drop physics edits")
    t.add_argument("asset", nargs="?")
    for name, sp in ps.choices.items():
        sp.set_defaults(fn=cmd_phys, cmdname=f"phys {name}")

    s = add("mesh", cmd_mesh, "mesh route: export vanilla mesh, Blender .blend/FBX, body-shape edits, check, Unreal build")
    xs = s.add_subparsers(dest="action", required=True, parser_class=Parser)
    t = xs.add_parser("export", description="export the skin's vanilla mesh (.uemodel + materials + PNG) via fmodel-mcp")
    t.add_argument("--lobby", action="store_true", help="also export the _Lobby mesh")
    t = xs.add_parser("blend", description="import the exported .uemodel into a .blend (headless Blender)")
    t.add_argument("--force", action="store_true", help="re-import over an existing .blend")
    xs.add_parser("fbx", description="export the .blend to build/fbx/*.fbx (no leaf bones)")
    t = xs.add_parser("inflate", description="weight-driven body-shape edit: grow or shrink the skin around bones")
    t.add_argument("--bone", action="append", required=True, help="bone name, e.g. L_Breast_01_Jnt (repeatable)")
    t.add_argument("--factor", type=float, default=1.2, help="1.2 = 20%% bigger, 0.9 = 10%% smaller")
    t.add_argument("--mesh", choices=["all", "game", "lobby"], default="all")
    t.add_argument("--no-children", action="store_true", help="only the named bones' own weights")
    t = xs.add_parser("preview", description="vanilla | edited renders (front, side) in build/preview/<mesh>.png")
    t.add_argument("--focus", help="bone to centre on, e.g. spine_04 (default: whole body)")
    xs.add_parser("check", description="bones, hierarchy, material slots and vertex groups must match vanilla")
    xs.add_parser("build", description="mrforge build with every exported mesh cooked (edited or not) through Unreal 5.3.2")
    for name, sp in xs.choices.items():
        sp.set_defaults(fn=cmd_mesh, cmdname=f"mesh {name}")

    add("build", cmd_build, "build every changed texture, material, physics asset and mesh into one mod container")
    s = add("validate", cmd_validate, "rules over the built mod; evidence tiers")
    s.add_argument("--quick", action="store_true", help="skip the round-trip extraction")
    add("package", cmd_package, "deterministic zip of the mod for a mod manager")
    s = add("deploy", cmd_deploy, "copy the mod into ~mods/<prefix>-mrforge-<id>/")
    s.add_argument("--prefix", help="folder prefix (default ZZZ, sorts after mod-manager folders)")
    s.add_argument("--status", action="store_true", help="list deployed forge mods")
    s = add("undeploy", cmd_undeploy, "remove a deployed forge mod (receipt-listed files only)")
    s.add_argument("id", nargs="?")
    s = add("selftest", cmd_selftest, "real-toolchain smoke run (no deploy)")
    s.add_argument("route", choices=["texture", "mesh", "physics"])
    s.add_argument("--lobby", action="store_true", help="mesh: also round-trip the lobby mesh")
    s.add_argument("--skin", default="1061303")
    s.add_argument("--texture")
    s.add_argument("--keep", action="store_true")
    s = add("check-load", cmd_checkload, "after an in-game look: deploy state, loader, log signatures; --confirm records it")
    s.add_argument("id", nargs="?")
    s.add_argument("--confirm", help="what you saw in game")
    s.add_argument("--tier", default="load", choices=["load", "gameplay"])
    return p


def _log(argv, code, secs):
    try:
        from .home import log_line
        log_line("cli", {"argv": [redact(a) for a in argv], "exit": code, "seconds": secs})
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    out = Out()
    t = time.time()
    command = argv[0] if argv else ""
    data = None
    pretty = "--pretty" in argv
    try:
        rest, g = split_globals(argv)
        pretty = g["pretty"]
        if rest and rest[0] in ("-h", "--help") or (len(rest) > 1 and rest[-1] in ("-h", "--help")):
            parser().parse_args(rest)  # prints help, exits 0
        args = parser().parse_args(rest)
        args.game, args.project = g["game"], g["project"]
        command = getattr(args, "cmdname", command)
        data = args.fn(args, out)
        code = 1 if out.errors else 0
    except ForgeError as e:
        out.errors.append(e.as_dict())
        data = e.data or None
        code = e.exit_code
    except KeyboardInterrupt:
        code = 130
    except SystemExit as e:  # --help
        return int(e.code or 0)
    except Exception as e:  # bugs are reported as JSON too
        out.errors.append({"code": "INTERNAL_ERROR", "message": f"{type(e).__name__}: {e}",
                           "fix": "report this with the command you ran",
                           "trace": traceback.format_exc().splitlines()[-6:]})
        code = 1
    res = {"ok": code == 0, "command": command, "version": __version__, "data": data,
           "errors": out.errors, "warnings": out.warnings, "gaps": out.gaps}
    text = json.dumps(res, indent=2 if pretty else None, ensure_ascii=False, default=str)
    sys.stdout.write(redact(text) + "\n")
    _log(argv, code, round(time.time() - t, 2))
    return code
