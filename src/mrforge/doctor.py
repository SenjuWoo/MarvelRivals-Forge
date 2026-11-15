"""mrforge doctor: one report on payload, toolchain, game, data and routes, each check with a fix."""
from __future__ import annotations

import shutil
import sys

from . import tools as T
from .util import ForgeError, KNOWLEDGE_DIR, run


def _c(id_, status, detail, fix=""):
    return {"id": id_, "status": status, "detail": detail, "fix": fix}


def payload_checks() -> list[dict]:
    out = []
    ok = sys.version_info >= (3, 10)
    out.append(_c("python", "ok" if ok else "fail", sys.version.split()[0], "" if ok else "install Python 3.10+"))
    try:
        import PIL
        out.append(_c("pillow", "ok", PIL.__version__))
    except ImportError:
        out.append(_c("pillow", "fail", "Pillow is not importable", "pip install Pillow (or run Install.ps1)"))
    need = ["facts.json", "routes.json", "errors.json", "skins.json", "texture_kinds.json"]
    missing = [n for n in need if not (KNOWLEDGE_DIR / n).is_file()]
    out.append(_c("knowledge", "fail" if missing else "ok", f"missing: {missing}" if missing else f"{len(need)} data files",
                  "reinstall the forge" if missing else ""))
    try:
        lk = T.lock()
        out.append(_c("tools_lock", "ok", f"{len(lk['tools'])} pinned tools"))
    except (OSError, ValueError) as e:
        out.append(_c("tools_lock", "fail", str(e), "restore tools.lock.json from the repository"))
    return out


def toolchain_checks() -> tuple[list[dict], dict]:
    out, state = [], {}
    try:
        lk = T.lock()
    except (OSError, ValueError):
        return out, state
    for t in lk["tools"]:
        st = T.status(t)
        optional = t.get("optional", False)
        bad = "warn" if optional else "fail"
        if not st["installed"]:
            out.append(_c(t["name"], bad, f"{t['tag']} not set up", "run: mrforge setup"))
            state[t["name"]] = False
            continue
        if not st["hash_ok"]:
            out.append(_c(t["name"], bad, "hash differs from tools.lock.json", "run: mrforge setup --force"))
            state[t["name"]] = False
            continue
        p = T.probe(t)
        state[t["name"]] = p["ok"]
        out.append(_c(t["name"], "ok" if p["ok"] else bad, p["output"], "" if p["ok"] else "run: mrforge setup --force"))
    try:
        dll = T.tool_dir(T.entry("uassettool")) / "oo2core_9_win64.dll"
        if state.get("uassettool"):
            present = dll.is_file()
            state["oodle"] = present
            out.append(_c("oodle", "ok" if present else "warn", "oo2core_9_win64.dll present" if present else
                          "missing; UAssetTool downloads it on the first extraction (needs network)",
                          "" if present else "run one extraction online, or mrforge setup --from <folder with the DLL>"))
    except ForgeError:
        pass
    return out, state


def game_checks(game_arg, flagged_scan: bool = True) -> tuple[list[dict], dict]:
    from . import game as G
    out, info = [], {}
    try:
        info = G.info(game_arg)
    except ForgeError as e:
        out.append(_c("game_found", "fail", e.message, e.fix))
        return out, {}
    out.append(_c("game_found", "ok", f"{info['root']} (via {info['source']})"))
    out.append(_c("game_build", "ok" if info["changelist"] else "fail", f"{info['version']} changelist {info['changelist']}",
                  "" if info["changelist"] else "verify game files in Steam"))
    ld = info["loader"]
    out.append(_c("loader", "ok" if ld["present"] else "warn",
                  f"ASI loader {'present' if ld['asi_loader'] else 'missing'}; plugins {ld['asi_plugins']}",
                  "" if ld["present"] else "install the ASI loader + UTOC signature bypass through your mod manager; mods will not load without it"))
    out.append(_c("mods_dir", "ok" if info["mods_dir_exists"] else "warn", info["mods_dir"],
                  "" if info["mods_dir_exists"] else "mrforge deploy creates it"))
    try:
        from .mesh import leftover_views
        lv = leftover_views(info["root"])
        if lv:
            out.append(_c("vanilla_views", "warn", f"leftover hardlink views: {lv}",
                          "delete them (they are hardlinks; deleting frees nothing the game needs)"))
    except OSError:
        pass
    if info["running"]:
        out.append(_c("game_running", "warn", "the game is running", "close it before deploy/undeploy"))
    if flagged_scan:
        try:
            from .mods import scan
            mods = scan(info["mods_dir"])
            flagged = [m for m in mods if m.get("flags_bad")]
            out.append(_c("flagged_mods", "warn" if flagged else "ok",
                          f"{len(flagged)} encrypted/obfuscated/stripped mods: " + ", ".join(m["name"] for m in flagged[:10])
                          if flagged else f"{len(mods)} mods scanned, none encrypted/obfuscated/stripped",
                          "since Season 11 the game reports such mods; remove or replace them" if flagged else ""))
        except ForgeError as e:
            out.append(_c("flagged_mods", "skip", e.message, e.fix))
    return out, info


def data_checks(info: dict) -> tuple[list[dict], dict]:
    from .sync import aes_key, usmap_for
    out, state = [], {}
    cl = info.get("changelist")
    if not cl:
        out.append(_c("usmap", "skip", "no game build known"))
        return out, state
    p = usmap_for(cl)
    state["usmap"] = bool(p)
    out.append(_c("usmap", "ok" if p else "fail", p.name if p else f"no mapping cached for build {cl}",
                  "" if p else "run: mrforge sync"))
    out.append(_c("aes_key", "ok" if aes_key() else "warn", "stored" if aes_key() else "not stored",
                  "" if aes_key() else "run: mrforge sync (needed for mesh export only)"))
    from .index import index_path
    ip = index_path(cl)
    state["index"] = ip.is_file()
    out.append(_c("index", "ok" if ip.is_file() else "warn", ip.name if ip.is_file() else "not built for this build",
                  "" if ip.is_file() else "run: mrforge index"))
    return out, state


def route_checks(tool_state: dict, data_state: dict) -> list[dict]:
    from .ue import detect
    out = []
    tex = tool_state.get("retoc-rivals-cli") and tool_state.get("uassettool") and data_state.get("usmap")
    out.append({"route": "texture", "status": "available" if tex else "unavailable",
                "needs": "retoc-rivals-cli + uassettool + exact usmap"})
    out.append({"route": "material", "status": "available" if tex else "unavailable",
                "needs": "same as texture (UAssetTool to_json/from_json)"})
    blender = shutil.which("blender")
    bver = None
    if blender:
        try:
            r = run([blender, "--version"], timeout=60)
            first = (r["stdout"].splitlines() or [""])[0]
            bver = first.replace("Blender", "").strip()
        except ForgeError:
            pass
    bok = False
    if bver:
        try:
            major, minor = (int(x) for x in bver.split(".")[:2])
            bok = (major, minor) >= (4, 2)
        except ValueError:
            pass
    mx = tool_state.get("fmodel-mcp") and tool_state.get("ueformat-blender") and bok and tool_state.get("oodle")
    out.append({"route": "mesh-export", "status": "available" if mx else "unavailable",
                "needs": "fmodel-mcp + ueformat-blender + Blender >= 4.2 + Oodle DLL",
                "blender": bver or "not on PATH", "release": "v0.2"})
    ue = detect()
    mb = ue["found"] and mx and tool_state.get("rivals-mesh-material-manager") and tool_state.get("uassettool")
    out.append({"route": "mesh-build", "status": "available" if mb else "unavailable",
                "needs": "mesh-export + Unreal Engine 5.3.2 + rivals-mesh-material-manager + uassettool", "ue": ue,
                "release": "v0.2"})
    out.append({"route": "physics", "status": "unavailable", "needs": "planned after v0.2", "release": "later"})
    return out


def run_doctor(game_arg=None) -> tuple[dict, bool]:
    sections = {"payload": payload_checks()}
    sections["toolchain"], tool_state = toolchain_checks()
    sections["game"], info = game_checks(game_arg, flagged_scan=bool(tool_state.get("retoc-rivals-cli")))
    sections["data"], data_state = data_checks(info) if info else ([], {})
    routes = route_checks(tool_state, data_state)
    hard_fail = any(c["status"] == "fail" for s in ("payload", "toolchain", "game") for c in sections[s])
    summary = {s: {k: sum(1 for c in v if c["status"] == k) for k in ("ok", "warn", "fail", "skip")}
               for s, v in sections.items()}
    return {"summary": summary, "sections": sections, "routes": routes,
            "game": {k: info.get(k) for k in ("root", "version", "changelist")} if info else None}, not hard_fail
