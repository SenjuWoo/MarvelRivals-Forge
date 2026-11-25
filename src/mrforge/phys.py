"""Physics route: KawaiiPhysics chains in the skin's post-process AnimBlueprint (Post_<skin>_Physics).

The vanilla asset is edited as UAssetTool (UAssetAPI) JSON; the anim graph itself is never changed (decision D23).
Structure (captured from Post_1061303_Physics, build 4066382): the class default object `Default__<name>_C` holds one
struct property per anim node in LinkID order; a node's input pose is a PoseLink/ComponentSpacePoseLink struct whose
`LinkID` indexes that list. AnimNode_KawaiiPhysics nodes carry `Chains` (array of KawaiiPhysicsChain); each chain has
BoneSettings (RootBone, AdditionalRootBones, DummyBoneLength, ...) and PhysicsSettings (PhysicsSettings struct with
Damping/Stiffness/... plus bUseCurve and curves). The game itself uses up to 11 chains per node.

Unversioned serialization keeps a per-struct header whose zero mask omits zero fields. When a zero field becomes
non-zero, the header of the struct holding it is dropped so UAssetTool rebuilds it (decision D25); the node-level
header is never dropped (that corrupts the export, verified).
"""
from __future__ import annotations

import copy
import fnmatch
from pathlib import Path

from .util import ForgeError, UsageError, load_json, save_json

KAWAII = "AnimNode_KawaiiPhysics"
POSE_LINKS = ("PoseLink", "ComponentSpacePoseLink")

# Chain parameters the forge edits: name -> path of struct names from the chain element.
PARAMS = {
    "Damping": ("PhysicsSettings", "PhysicsSettings"),
    "Stiffness": ("PhysicsSettings", "PhysicsSettings"),
    "WorldDampingLocation": ("PhysicsSettings", "PhysicsSettings"),
    "WorldDampingRotation": ("PhysicsSettings", "PhysicsSettings"),
    "Radius": ("PhysicsSettings", "PhysicsSettings"),
    "LimitAngle": ("PhysicsSettings", "PhysicsSettings"),
    "LimitLinear": ("PhysicsSettings", "PhysicsSettings"),
    "GravityScale": ("PhysicsSettings", "PhysicsSettings"),
    "bUseCurve": ("PhysicsSettings",),
    "TeleportDistanceThreshold": ("PhysicsSettings",),
    "TeleportRotationThreshold": ("PhysicsSettings",),
    "DummyBoneLength": ("BoneSettings",),
}
BOOL_PARAMS = {"bUseCurve"}

# Starting points for soft-tissue chains. KawaiiPhysics semantics: Damping slows the bones (higher = calmer),
# Stiffness pulls them back to the animated pose, WorldDamping* = how much of the character's own movement the bones
# ignore (lower = more follow-through), LimitAngle caps the swing, DummyBoneLength adds a virtual tip (cm) so the
# last real bone rotates too.
PRESETS = {
    "jiggle": {"Damping": 0.15, "Stiffness": 0.08, "WorldDampingLocation": 0.7, "WorldDampingRotation": 0.7,
               "Radius": 2.0, "LimitAngle": 25.0, "GravityScale": 0.2, "DummyBoneLength": 6.0, "bUseCurve": False},
    "bouncy": {"Damping": 0.08, "Stiffness": 0.04, "WorldDampingLocation": 0.5, "WorldDampingRotation": 0.5,
               "Radius": 2.0, "LimitAngle": 35.0, "GravityScale": 0.3, "DummyBoneLength": 7.0, "bUseCurve": False},
    "firm": {"Damping": 0.3, "Stiffness": 0.2, "WorldDampingLocation": 0.85, "WorldDampingRotation": 0.85,
             "Radius": 2.0, "LimitAngle": 15.0, "GravityScale": 0.1, "DummyBoneLength": 4.0, "bUseCurve": False},
}


# Spring-bone jiggle (editor-built route, uepost.py). "reference" = the values a working community lobby-jiggle mod
# uses (stiffness 80, damping 6, 3 cm); AnimNode_SpringBone moves the bone itself, so springs go on the bones that
# carry the soft tissue (on 1061: L/R_Breast_01_Jnt and _02_Jnt, L/R_ButtScale).
SPRING_PRESETS = {
    "reference": {"stiffness": 80.0, "damping": 6.0, "max_displacement": 3.0},
    "soft": {"stiffness": 50.0, "damping": 4.0, "max_displacement": 4.0},
    "firm": {"stiffness": 120.0, "damping": 10.0, "max_displacement": 2.0},
}
EDITOR_OPS = ("springs",)


def spring_params(preset: str | None, stiffness=None, damping=None, max_displacement=None, rotate=False) -> dict:
    if preset and preset not in SPRING_PRESETS:
        raise UsageError(f"unknown spring preset {preset!r}", f"one of: {', '.join(SPRING_PRESETS)}")
    p = dict(SPRING_PRESETS[preset or "reference"])
    for k, v in (("stiffness", stiffness), ("damping", damping), ("max_displacement", max_displacement)):
        if v is not None:
            if v <= 0:
                raise UsageError(f"{k} must be > 0")
            p[k] = float(v)
    p.update(limit=True, translate=[True, True, True], rotate=[bool(rotate)] * 3)
    return p


def editor_ops(ops: list[dict]) -> list[dict]:
    return [o for o in ops if o["op"] in EDITOR_OPS]


def json_ops(ops: list[dict]) -> list[dict]:
    return [o for o in ops if o["op"] not in EDITOR_OPS]


def verify_springs(d: dict, ops: list[dict]) -> list[str]:
    """Problems: a requested spring missing from (or different in) the built blueprint, or not feeding the output."""
    probs = []
    try:
        nodes = anim_nodes(d)
    except ForgeError as e:
        return [e.message]
    order = set(eval_order(d))
    springs = {}
    for i, n in enumerate(nodes):
        if n.get("StructType") == "AnimNode_SpringBone":
            try:
                bone = child(child(n, "SpringBone"), "BoneName").get("Value")
            except ForgeError:
                continue
            springs[bone] = (i, n)
    for op in editor_ops(ops):
        for bone in op["bones"]:
            if bone not in springs:
                probs.append(f"spring on {bone} missing")
                continue
            i, n = springs[bone]
            if i not in order:
                probs.append(f"spring on {bone} does not feed the output pose")
            for k, field in (("stiffness", "SpringStiffness"), ("damping", "SpringDamping"),
                             ("max_displacement", "MaxDisplacement")):
                want = op.get("params", {}).get(k)
                try:
                    got = _num(child(n, field).get("Value"))
                except ForgeError:
                    got = 0.0  # unversioned zero is omitted
                if want is not None and abs(float(got) - float(want)) > 1e-3:
                    probs.append(f"spring {bone}.{field} = {got}, expected {want}")
    return probs


# --- JSON access ----------------------------------------------------------------

def _num(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("+", ""))
    except ValueError:
        return v


def _is_zero(v) -> bool:
    n = _num(v)
    return n is None or n is False or (isinstance(n, float) and n == 0.0)


def cdo(d: dict) -> list:
    for e in d.get("Exports", []):
        if str(e.get("ObjectName", "")).startswith("Default__"):
            data = e.get("Data")
            if not isinstance(data, list):
                raise ForgeError("PHYS_UNPARSED", f"{e.get('ObjectName')} did not parse with the mappings (raw export)",
                                 "check the usmap matches the game build (mrforge sync)")
            return data
    raise ForgeError("NOT_AN_ANIM_BLUEPRINT", "no class default object in this JSON")


def child(node: dict, name: str) -> dict:
    for q in node.get("Value") or []:
        if isinstance(q, dict) and q.get("Name") == name:
            return q
    raise ForgeError("PHYS_FIELD_MISSING", f"{node.get('Name')} has no field {name!r}")


def _walk(v, fn):
    if isinstance(v, dict):
        fn(v)
        if isinstance(v.get("Value"), list):
            for x in v["Value"]:
                _walk(x, fn)
    elif isinstance(v, list):
        for x in v:
            _walk(x, fn)


def _links(node: dict) -> list[int]:
    out = []

    def fn(v):
        if v.get("StructType") in POSE_LINKS:
            for x in v.get("Value") or []:
                if isinstance(x, dict) and x.get("Name") == "LinkID" and isinstance(x.get("Value"), int):
                    out.append(x["Value"])
    for x in node.get("Value") or []:
        _walk(x, fn)
    return out


def anim_nodes(d: dict) -> list[dict]:
    """Anim node properties of the CDO in LinkID order (index = LinkID)."""
    return [p for p in cdo(d) if str(p.get("StructType", "")).startswith("AnimNode_")]


def eval_order(d: dict) -> list[int]:
    """Node indices from the graph input to the Root, following pose links (depth-first, inputs before users)."""
    nodes = anim_nodes(d)
    root = next((i for i, p in enumerate(nodes) if p.get("StructType") == "AnimNode_Root"), None)
    if root is None:
        return list(range(len(nodes)))
    order, seen = [], set()

    def visit(i):
        if i in seen or not (0 <= i < len(nodes)):
            return
        seen.add(i)
        for j in _links(nodes[i]):
            visit(j)
        order.append(i)
    visit(root)
    return order


def _chain_list(node: dict) -> list:
    return child(node, "Chains").get("Value") or []


def roots_of(chain: dict) -> list[str]:
    bs = child(chain, "BoneSettings")
    out = [child(child(bs, "RootBone"), "BoneName").get("Value")]
    for extra in child(bs, "AdditionalRootBones").get("Value") or []:
        try:
            out.append(child(child(extra, "RootBone"), "BoneName").get("Value"))
        except ForgeError:
            pass
    return [r for r in out if r]


def _param_holder(chain: dict, name: str) -> list[dict]:
    """[outer struct, ..., struct holding the field] for a chain parameter."""
    path = PARAMS.get(name)
    if not path:
        raise UsageError(f"unknown physics parameter {name!r}", f"one of: {', '.join(sorted(PARAMS))}")
    cur, chain_of = chain, []
    for p in path:
        cur = child(cur, p)
        chain_of.append(cur)
    return chain_of


def get_param(chain: dict, name: str):
    return _num(child(_param_holder(chain, name)[-1], name).get("Value"))


def set_param(chain: dict, name: str, value) -> None:
    holders = _param_holder(chain, name)
    field = child(holders[-1], name)
    if name in BOOL_PARAMS:
        value = bool(value)
    else:
        value = float(value)
    if _is_zero(field.get("Value")) and not _is_zero(value):
        holders[-1]["OriginalStructHeader"] = None  # the zero mask would keep omitting the field (D25)
    field["Value"] = value
    field["IsZero"] = False


def kawaii_nodes(d: dict) -> list[tuple[int, dict]]:
    return [(i, p) for i, p in enumerate(anim_nodes(d)) if p.get("StructType") == KAWAII]


def listing(d: dict) -> dict:
    nodes = anim_nodes(d)
    order = eval_order(d)
    pos = {i: n for n, i in enumerate(order)}
    out = []
    for i, p in kawaii_nodes(d):
        for ci, ch in enumerate(_chain_list(p)):
            out.append({"node": p["Name"], "link": i, "eval": pos.get(i), "chain": ci, "roots": roots_of(ch),
                        "params": {k: get_param(ch, k) for k in PARAMS}})
    out.sort(key=lambda x: (x["eval"] if x["eval"] is not None else 1 << 30, x["chain"]))
    host = default_host(d)
    return {"anim_nodes": len(nodes), "kawaii_nodes": len(kawaii_nodes(d)), "chains": out,
            "default_host": host, "bones_in_name_map": len(d.get("NameMap", []))}


def default_host(d: dict) -> str | None:
    """The KawaiiPhysics node evaluated last: a chain there runs after every constraint/rivet node (D24)."""
    nodes = anim_nodes(d)
    ks = [i for i in eval_order(d) if nodes[i].get("StructType") == KAWAII]
    return nodes[ks[-1]]["Name"] if ks else None


def find_node(d: dict, name: str) -> dict:
    for _, p in kawaii_nodes(d):
        if p["Name"] == name:
            return p
    raise ForgeError("PHYS_NODE_NOT_FOUND", f"no KawaiiPhysics node {name!r}", "mrforge phys list shows the nodes")


def select_chains(d: dict, node: str | None = None, bone: str | None = None, chain: int | None = None) -> list[tuple[str, int, dict]]:
    out = []
    for _, p in kawaii_nodes(d):
        if node and p["Name"] != node:
            continue
        for ci, ch in enumerate(_chain_list(p)):
            if chain is not None and ci != chain:
                continue
            if bone and not any(fnmatch.fnmatchcase(r, bone) for r in roots_of(ch)):
                continue
            out.append((p["Name"], ci, ch))
    return out


def add_chain(d: dict, root_bone: str, params: dict, host: str | None = None) -> dict:
    """Append one chain rooted at root_bone to the host node, copied from the host's first chain."""
    host = host or default_host(d)
    if not host:
        raise ForgeError("PHYS_NO_KAWAII_NODE", "this AnimBlueprint has no KawaiiPhysics node to host a chain",
                         "lobby post-process assets often have none; edit the in-match Post_<skin>_Physics instead")
    for name, ci, ch in select_chains(d):
        if root_bone in roots_of(ch):
            raise ForgeError("PHYS_BONE_ALREADY_SIMULATED", f"{root_bone} already roots {name} chain {ci}",
                             f"tune it instead: mrforge phys set --bone {root_bone} <Param> <value>")
    node = find_node(d, host)
    chains = child(node, "Chains")
    if not chains.get("Value"):
        raise ForgeError("PHYS_NO_TEMPLATE", f"{host} has no chain to copy", "pick another --host")
    el = copy.deepcopy(chains["Value"][0])
    el["Name"] = str(len(chains["Value"]))
    bs = child(el, "BoneSettings")
    child(child(bs, "RootBone"), "BoneName")["Value"] = root_bone
    for lst in ("AdditionalRootBones", "ExcludeBones"):
        try:
            child(bs, lst)["Value"] = []
        except ForgeError:
            pass
    for k, v in params.items():
        set_param(el, k, v)
    names = d.setdefault("NameMap", [])
    if root_bone not in names:
        names.append(root_bone)
    chains["Value"].append(el)
    return {"host": host, "chain": int(el["Name"]), "root": root_bone, "params": {k: get_param(el, k) for k in PARAMS}}


def parse_params(pairs: list[str] | None, preset: str | None) -> dict:
    if preset and preset not in PRESETS:
        raise UsageError(f"unknown preset {preset!r}", f"one of: {', '.join(PRESETS)}")
    out = dict(PRESETS[preset]) if preset else {}
    for pr in pairs or []:
        if "=" not in pr:
            raise UsageError(f"{pr!r} is not Param=value", "e.g. --param Damping=0.2")
        k, v = pr.split("=", 1)
        k = k.strip()
        if k not in PARAMS:
            raise UsageError(f"unknown physics parameter {k!r}", f"one of: {', '.join(sorted(PARAMS))}")
        out[k] = v.strip().lower() in ("1", "true", "yes", "on") if k in BOOL_PARAMS else float(v)
    return out


# --- ops (recorded, re-applied on build) -------------------------------------------

def ops_path(root: Path) -> Path:
    return Path(root) / "work" / "phys_ops.json"


def load_ops(root: Path) -> dict:
    return load_json(ops_path(root), {"assets": {}})


def apply_ops(d: dict, ops: list[dict]) -> list[dict]:
    done = []
    for op in json_ops(ops):
        if op["op"] == "add_chain":
            done.append(add_chain(d, op["root"], op.get("params", {}), op.get("host")))
        elif op["op"] == "set":
            hits = select_chains(d, op.get("node"), op.get("bone"), op.get("chain"))
            if not hits:
                raise ForgeError("PHYS_NO_MATCH", f"no chain matches {op}", "mrforge phys list")
            for name, ci, ch in hits:
                set_param(ch, op["param"], op["value"])
            done.append({"set": op["param"], "value": op["value"], "chains": [f"{n}[{c}]" for n, c, _ in hits]})
        else:
            raise ForgeError("PHYS_BAD_OP", f"unknown op {op.get('op')}")
    return done


def verify(d: dict, ops: list[dict]) -> list[str]:
    """Problems: an op whose result is not in d (d = JSON read back from a built asset)."""
    probs = []
    ops = json_ops(ops)
    if not ops:
        return []
    try:
        chains = select_chains(d)
    except ForgeError as e:
        return [e.message]
    for op in ops:
        params = op.get("params", {}) if op["op"] == "add_chain" else {op["param"]: op["value"]}
        if op["op"] == "add_chain":
            hits = [(n, c, ch) for n, c, ch in chains if op["root"] in roots_of(ch)]
            if not hits:
                probs.append(f"chain rooted at {op['root']} missing")
                continue
        else:
            hits = select_chains(d, op.get("node"), op.get("bone"), op.get("chain"))
            if not hits:
                probs.append(f"no chain matches {op.get('node') or ''}{op.get('bone') or ''}")
                continue
        for n, c, ch in hits:
            for k, want in params.items():
                got = get_param(ch, k)
                ok = (bool(got) == bool(want)) if k in BOOL_PARAMS else (isinstance(got, float) and abs(got - float(want)) < 1e-4)
                if not ok:
                    probs.append(f"{n}[{c}].{k} = {got}, expected {want}")
    return probs


def record(root: Path, lock: dict, asset: str | None, op: dict) -> list[dict]:
    """Validate an op against the current state of each target asset, then store it."""
    keys = resolve_keys(lock, asset, editor=op["op"] in EDITOR_OPS)
    ops = load_ops(root)
    out = []
    for key in keys:
        have = ops["assets"].get(key, [])
        if (op["op"] in EDITOR_OPS and json_ops(have)) or (op["op"] not in EDITOR_OPS and editor_ops(have)):
            raise ForgeError("PHYS_ROUTE_MIX", f"{key} already has {'chain' if json_ops(have) else 'spring'} edits",
                             "one asset is edited either by JSON chains (add-chain/set) or rebuilt with springs; "
                             f"mrforge phys reset {key} first")
        if op["op"] in EDITOR_OPS:
            dup = [b for b in op["bones"] if any(b in o["bones"] for o in editor_ops(have))]
            if dup:
                raise ForgeError("PHYS_BONE_ALREADY_SIMULATED", f"springs already on {dup}", f"mrforge phys reset {key}")
            ops["assets"].setdefault(key, []).append(op)
            out.append({"asset": key, "result": [{"springs": op["bones"], "params": op["params"]}]})
            continue
        d = base_json(root, lock, key)
        apply_ops(d, ops["assets"].get(key, []))  # earlier ops first: a bone added before can be tuned now
        res = apply_ops(d, [op])
        ops["assets"].setdefault(key, []).append(op)
        out.append({"asset": key, "result": res})
    save_json(ops_path(root), ops)
    return out


def resolve_keys(lock: dict, asset: str | None, editor: bool = False) -> list[str]:
    ph = lock.get("physics", {})
    if not ph:
        raise ForgeError("PHYSICS_NOT_EXTRACTED", "no physics asset extracted", "mrforge extract --physics")
    if not asset and editor:
        lobby = [k for k in ph if k.endswith("_Lobby_Physics")]
        if not lobby:
            raise ForgeError("PHYS_NO_LOBBY_ASSET", "no lobby post-process asset extracted",
                             "pass --asset Post_<skin>_Physics, or mrforge extract --physics")
        return lobby
    if not asset:
        with_kawaii = [k for k, v in ph.items() if v.get("kawaii_nodes")]
        if not with_kawaii:
            raise ForgeError("PHYS_NO_KAWAII_NODE", "no extracted physics asset has KawaiiPhysics nodes",
                             "mrforge phys list shows what each asset contains")
        return with_kawaii
    hits = [k for k in ph if k == asset or k.lower() == asset.lower() or fnmatch.fnmatchcase(k, asset)]
    if not hits:
        raise ForgeError("PHYSICS_NOT_EXTRACTED", f"no extracted physics asset matches {asset!r}",
                         f"extracted: {', '.join(sorted(ph))}")
    return sorted(hits)


def base_json(root: Path, lock: dict, key: str) -> dict:
    return load_json(Path(root) / lock["physics"][key]["work_json"])


def apply(root: Path, lock: dict, key: str) -> dict:
    d = base_json(root, lock, key)
    apply_ops(d, load_ops(root)["assets"].get(key, []))
    return d
