"""Material instance parameters on UAssetTool's UAssetAPI JSON: read, set, record as ops.

Structure (captured from MI_1061303_Body_01): Exports[0].Data has ScalarParameterValues /
VectorParameterValues / TextureParameterValues arrays; each entry's Value[0] is ParameterInfo (Value[0] = Name),
Value[1] is ParameterValue (float, LinearColor struct, or an import index). Zero floats can be strings "+0"/"-0".
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import ForgeError, UsageError, load_json, save_json

_LINEAR_COLOR = {"$type": "UAssetAPI.PropertyTypes.Structs.LinearColorPropertyData, UAssetAPI", "Name": "ParameterValue",
                 "ArrayIndex": 0, "IsZero": False, "PropertyTagFlags": "None", "PropertyTagExtensions": "NoExtension",
                 "Value": {"$type": "UAssetAPI.UnrealTypes.FLinearColor, UAssetAPI", "R": 0.0, "G": 0.0, "B": 0.0, "A": 0.0}}

ARRAYS = {"ScalarParameterValues": "scalar", "VectorParameterValues": "vector", "TextureParameterValues": "texture"}


def num(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace("+", ""))


def _export(d: dict) -> dict:
    for e in d.get("Exports", []):
        if any(p.get("Name") in ARRAYS for p in e.get("Data", []) or []):
            return e
    raise ForgeError("NOT_A_MATERIAL_INSTANCE", "no parameter arrays in this JSON")


def _import_path(d: dict, idx) -> str | None:
    try:
        i = int(idx)
    except (TypeError, ValueError):
        return None
    if i >= 0:
        return None
    imps = d.get("Imports", [])
    if -i > len(imps):
        return None
    imp = imps[-i - 1]
    outer = imp.get("OuterIndex", 0)
    if outer and outer < 0 and -outer <= len(imps):
        return f"{imps[-outer - 1]['ObjectName']}.{imp['ObjectName']}"
    return imp["ObjectName"]


def _entry_name(ent: dict) -> str:
    return ent["Value"][0]["Value"][0]["Value"]


def params(d: dict) -> list[dict]:
    out = []
    for p in _export(d).get("Data", []):
        kind = ARRAYS.get(p.get("Name"))
        if not kind:
            continue
        for ent in p.get("Value", []):
            name = _entry_name(ent)
            pv = ent["Value"][1]
            if kind == "scalar":
                val = num(pv["Value"]) if pv.get("Value") is not None else 0.0
            elif kind == "vector":
                if not pv.get("Value"):  # zero colour: unversioned serialization omits the value (IsZero)
                    val = [0.0, 0.0, 0.0, 0.0]
                else:
                    c = pv["Value"][0]["Value"]
                    val = [round(num(c[k]), 6) for k in ("R", "G", "B", "A")]
            else:
                val = _import_path(d, pv.get("Value"))
            out.append({"name": name, "type": kind, "value": val})
    return out


def parent(d: dict) -> str | None:
    for p in _export(d).get("Data", []):
        if p.get("Name") == "Parent":
            return _import_path(d, p.get("Value"))
    return None


def package_refs(d: dict) -> list[str]:
    return sorted({i["ObjectName"] for i in d.get("Imports", []) if i.get("ClassName") == "Package"
                   and str(i.get("ObjectName", "")).startswith("/Game/")})


def parse_value(kind: str, text: str):
    t = str(text).strip()
    if kind == "scalar":
        try:
            return float(t)
        except ValueError as e:
            raise UsageError(f"{t!r} is not a number", "scalar parameters take one number, e.g. 0.5") from e
    if kind == "vector":
        if re.fullmatch(r"#?[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", t):
            h = t.lstrip("#")
            vals = [int(h[i:i + 2], 16) / 255.0 for i in range(0, len(h), 2)]
            if len(vals) == 3:
                vals.append(1.0)
            return [round(v, 6) for v in vals]
        parts = [x for x in re.split(r"[,\s]+", t) if x]
        try:
            vals = [float(x) for x in parts]
        except ValueError as e:
            raise UsageError(f"{t!r} is not a colour", "use r,g,b[,a] (0-1, HDR allowed) or #rrggbb") from e
        if len(vals) == 3:
            vals.append(1.0)
        if len(vals) != 4:
            raise UsageError(f"{t!r} needs 3 or 4 numbers", "use r,g,b[,a]")
        return vals
    raise UsageError("texture parameters cannot be set in v0.1",
                     "change the texture itself with mrforge tex ... instead")


def set_param(d: dict, name: str, value) -> dict:
    for p in _export(d).get("Data", []):
        kind = ARRAYS.get(p.get("Name"))
        if not kind:
            continue
        for ent in p.get("Value", []):
            if _entry_name(ent) != name:
                continue
            pv = ent["Value"][1]
            if kind == "scalar":
                pv["Value"] = float(value)
            elif kind == "vector":
                if not pv.get("Value"):
                    # Zero colour had no serialized value. Add one and drop the captured unversioned header,
                    # whose zero mask would otherwise keep writing the field as zero (verified 2026-11-15).
                    pv["Value"] = [dict(_LINEAR_COLOR, Value=dict(_LINEAR_COLOR["Value"]))]
                    pv["IsZero"] = False
                    ent["OriginalStructHeader"] = None
                c = pv["Value"][0]["Value"]
                for k, v in zip(("R", "G", "B", "A"), value):
                    c[k] = float(v)
            else:
                raise UsageError("texture parameters cannot be set in v0.1")
            return {"name": name, "type": kind, "value": value}
    raise ForgeError("PARAM_NOT_FOUND", f"parameter {name!r} is not set on this material instance",
                     "mrforge mat list <material> shows the parameters it overrides; parameters only on the parent cannot be added in v0.1")


# --- project integration ----------------------------------------------------

def ops_path(root: Path) -> Path:
    return Path(root) / "work" / "mat_ops.json"


def load_ops(root: Path) -> dict:
    return load_json(ops_path(root), {"materials": {}})


def resolve_keys(lock: dict, name: str) -> list[str]:
    mats = lock.get("materials", {})
    if name in mats:
        return [name]
    n = name.replace("\\", "/")
    hits = [k for k in mats if k.endswith("/" + n) or k.split("/")[-1] == n]
    if not hits:
        raise ForgeError("MATERIAL_NOT_EXTRACTED", f"no extracted material matches {name!r}",
                         "mrforge mat list shows extracted materials; mrforge extract --materials extracts them")
    return sorted(hits)


def base_json(root: Path, lock: dict, key: str) -> dict:
    """Work JSON when hand-edited, otherwise the pristine vanilla JSON."""
    rec = lock["materials"][key]
    return load_json(Path(root) / rec["work_json"])


def record(root: Path, lock: dict, name: str, param: str, text: str) -> list[dict]:
    keys = resolve_keys(lock, name)
    ops = load_ops(root)
    done = []
    for key in keys:
        d = base_json(root, lock, key)
        cur = {p["name"]: p for p in params(d)}
        if param not in cur:
            raise ForgeError("PARAM_NOT_FOUND", f"{key} has no parameter {param!r}",
                             f"available: {', '.join(sorted(cur))}")
        value = parse_value(cur[param]["type"], text)
        ops["materials"].setdefault(key, {})[param] = value
        done.append({"material": key, "param": param, "type": cur[param]["type"], "old": cur[param]["value"], "new": value})
    save_json(ops_path(root), ops)
    return done


def apply(root: Path, lock: dict, key: str) -> dict:
    d = base_json(root, lock, key)
    for param, value in load_ops(root)["materials"].get(key, {}).items():
        set_param(d, param, value)
    return d
