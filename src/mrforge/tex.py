"""Texture edits as recorded, re-playable ops (Pillow). Every build regenerates work PNGs from vanilla PNGs.

work/ops.json: {"textures": {name: {"ops": [...], "generated_sha256": ...}}}
A texture without ops counts as changed when its work PNG differs from vanilla (hand-painted).
A texture with ops whose work PNG no longer matches the last generated output was hand-edited after the
ops ran; regenerating would lose that paint, so the forge stops with HAND_EDIT_CONFLICT.
"""
from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path

from .util import ForgeError, KNOWLEDGE_DIR, UsageError, load_json, save_json, sha256_file

COLOUR_OPS = ("hue", "tint", "levels")


def _img():
    try:
        from PIL import Image
        return Image
    except ImportError as e:
        raise ForgeError("PILLOW_MISSING", "Pillow is not installed", "pip install Pillow (or run Install.ps1)") from e


def kind_of(name: str) -> dict:
    data = load_json(KNOWLEDGE_DIR / "texture_kinds.json")
    for k in sorted(data["kinds"], key=lambda k: -len(k["suffix"])):
        if name.upper().endswith(k["suffix"].upper()):
            return k
    return {"suffix": "", **data["default"]}


def ops_path(root: Path) -> Path:
    return Path(root) / "work" / "ops.json"


def load_ops(root: Path) -> dict:
    return load_json(ops_path(root), {"textures": {}})


def save_ops(root: Path, ops: dict) -> None:
    save_json(ops_path(root), ops)


def parse_color(text: str) -> tuple[int, int, int]:
    t = text.strip().lstrip("#")
    if len(t) == 6:
        try:
            return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            pass
    parts = [p for p in t.replace(" ", ",").split(",") if p]
    if len(parts) == 3:
        try:
            vals = [float(p) for p in parts]
            if all(v <= 1.0 for v in vals):
                vals = [v * 255 for v in vals]
            return tuple(int(round(max(0, min(255, v)))) for v in vals)  # type: ignore[return-value]
        except ValueError:
            pass
    raise UsageError(f"{text!r} is not a colour", "use #rrggbb or r,g,b")


# --- pure image ops (deterministic) ------------------------------------------

def op_hue(img, shift: float):
    Image = _img()
    rgba = img.convert("RGBA")
    a = rgba.getchannel("A")
    h, s, v = rgba.convert("RGB").convert("HSV").split()
    off = int(round((shift % 360) / 360.0 * 256)) % 256
    h = h.point(lambda x: (x + off) % 256)
    out = Image.merge("HSV", (h, s, v)).convert("RGB").convert("RGBA")
    out.putalpha(a)
    return out


def op_tint(img, color: tuple[int, int, int], strength: float):
    Image = _img()
    rgba = img.convert("RGBA")
    a = rgba.getchannel("A")
    gray = rgba.convert("L")
    chans = [gray.point(lambda x, c=c: x * c // 255) for c in color]
    tinted = Image.merge("RGB", chans)
    out = Image.blend(rgba.convert("RGB"), tinted, max(0.0, min(1.0, strength))).convert("RGBA")
    out.putalpha(a)
    return out


def op_levels(img, black: int, white: int, gamma: float):
    if not (0 <= black < white <= 255) or gamma <= 0:
        raise UsageError("levels need 0 <= black < white <= 255 and gamma > 0")
    rgba = img.convert("RGBA")
    lut = []
    for x in range(256):
        t = min(1.0, max(0.0, (x - black) / float(white - black)))
        lut.append(int(round((t ** (1.0 / gamma)) * 255)))
    r, g, b, a = rgba.split()
    Image = _img()
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))


def op_overlay(img, overlay_path: Path, opacity: float, at: tuple[int, int] | None):
    Image = _img()
    base = img.convert("RGBA")
    ov = Image.open(overlay_path).convert("RGBA")
    if at is None:
        ov = ov.resize(base.size, Image.LANCZOS)
        pos = (0, 0)
    else:
        pos = at
    if opacity < 1.0:
        alpha = ov.getchannel("A").point(lambda x: int(x * max(0.0, opacity)))
        ov.putalpha(alpha)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(ov, pos)
    out = Image.alpha_composite(base, layer)
    out.putalpha(base.getchannel("A"))  # keep the vanilla alpha (it is often a mask channel)
    return out


def op_replace(img, src: Path, keep_size: bool):
    Image = _img()
    new = Image.open(src).convert("RGBA")
    if not keep_size and new.size != img.size:
        new = new.resize(img.size, Image.LANCZOS)
    return new


def apply_mask(original, edited, mask_path: Path):
    Image = _img()
    m = Image.open(mask_path).convert("L")
    if m.size != original.size:
        m = m.resize(original.size, Image.LANCZOS)
    if edited.size != original.size:
        return edited
    return Image.composite(edited.convert("RGBA"), original.convert("RGBA"), m)


def run_ops(vanilla_png: Path, ops: list[dict], sources: Path):
    Image = _img()
    img = Image.open(vanilla_png).convert("RGBA")
    img.load()
    for op in ops:
        before = img
        k = op["op"]
        if k == "hue":
            img = op_hue(img, op["shift"])
        elif k == "tint":
            img = op_tint(img, tuple(op["color"]), op["strength"])
        elif k == "levels":
            img = op_levels(img, op["black"], op["white"], op["gamma"])
        elif k == "overlay":
            img = op_overlay(img, sources / op["file"], op.get("opacity", 1.0), tuple(op["at"]) if op.get("at") else None)
        elif k == "replace":
            img = op_replace(img, sources / op["file"], op.get("keep_size", False))
        else:
            raise ForgeError("UNKNOWN_OP", f"unknown texture op {k!r} in ops.json")
        if op.get("mask"):
            img = apply_mask(before, img, sources / op["mask"])
    return img


# --- project integration ----------------------------------------------------

def textures(lock: dict) -> dict:
    return lock.get("textures", {})


def match(lock: dict, pattern: str) -> list[str]:
    names = [n for n in textures(lock) if fnmatch.fnmatchcase(n, pattern) or n == pattern]
    if not names:
        raise ForgeError("TEXTURE_NOT_EXTRACTED", f"no extracted texture matches {pattern!r}",
                         "mrforge tex list; mrforge extract --textures <glob>")
    return sorted(names)


def _copy_source(root: Path, src: str | None, prefix: str) -> str | None:
    if not src:
        return None
    p = Path(src)
    if not p.is_file():
        raise UsageError(f"file not found: {src}")
    dest_dir = Path(root) / "work" / "sources"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{sha256_file(p)[:12]}{p.suffix.lower()}"
    if not (dest_dir / name).exists():
        shutil.copyfile(p, dest_dir / name)
    return name


def add_op(root: Path, lock: dict, pattern: str, op: dict, force: bool = False, mask: str | None = None,
           src: str | None = None) -> dict:
    names = match(lock, pattern)
    warnings = []
    if op["op"] in COLOUR_OPS:
        for n in names:
            k = kind_of(n)
            if k["colour_ops"] == "refused" and not force:
                raise ForgeError("COLOUR_OP_ON_NORMAL_MAP", f"{n} is a {k['kind']} map: {k['note']}",
                                 "edit the _D colour texture instead, or pass --force if you really mean it")
            if k["colour_ops"] == "warn":
                warnings.append(f"{n}: {k['note']}")
    if src:
        op["file"] = _copy_source(root, src, op["op"])
    if mask:
        op["mask"] = _copy_source(root, mask, "mask")
    ops = load_ops(root)
    for n in names:
        if op["op"] != "replace":  # replace is the documented way to capture hand paint
            _check_hand_edit(root, lock, ops, n)
        rec = ops["textures"].setdefault(n, {"ops": []})
        if op["op"] == "replace":
            rec["ops"] = []  # a replace makes earlier ops on this texture meaningless
        rec["ops"].append(dict(op))
    save_ops(root, ops)
    regenerated = [regenerate(root, lock, n, ops) for n in names]
    save_ops(root, ops)
    return {"textures": names, "op": op, "warnings": warnings, "outputs": regenerated}


def _check_hand_edit(root: Path, lock: dict, ops: dict, name: str) -> None:
    rec = ops["textures"].get(name)
    work = Path(root) / lock["textures"][name]["work_png"]
    if rec and rec.get("ops") and rec.get("generated_sha256") and work.is_file():
        if sha256_file(work) != rec["generated_sha256"]:
            raise ForgeError("HAND_EDIT_CONFLICT", f"{work.name} was painted after its ops ran; regenerating would lose that paint",
                             f"capture it first: mrforge tex replace {name} <copy of the painted PNG>")
    if (not rec or not rec.get("ops")) and work.is_file():
        if sha256_file(work) != lock["textures"][name]["png_sha256"]:
            raise ForgeError("HAND_EDIT_CONFLICT", f"{work.name} has hand paint and no ops; an op would overwrite it",
                             f"capture it first: mrforge tex replace {name} <copy of the painted PNG>")


def regenerate(root: Path, lock: dict, name: str, ops: dict) -> str:
    t = lock["textures"][name]
    work = Path(root) / t["work_png"]
    vanilla = Path(root) / t["vanilla_png"]
    rec = ops["textures"].get(name)
    if not rec or not rec.get("ops"):
        shutil.copyfile(vanilla, work)
        if rec is not None:
            rec.pop("generated_sha256", None)
        return t["work_png"]
    img = run_ops(vanilla, rec["ops"], Path(root) / "work" / "sources")
    work.parent.mkdir(parents=True, exist_ok=True)
    img.save(work, format="PNG", optimize=False)
    rec["generated_sha256"] = sha256_file(work)
    return t["work_png"]


def regenerate_all(root: Path, lock: dict) -> list[str]:
    ops = load_ops(root)
    out = []
    for name, rec in ops["textures"].items():
        if rec.get("ops") and name in lock.get("textures", {}):
            _check_hand_edit(root, lock, ops, name)
            out.append(regenerate(root, lock, name, ops))
    save_ops(root, ops)
    return out


def reset(root: Path, lock: dict, pattern: str) -> list[str]:
    names = match(lock, pattern)
    ops = load_ops(root)
    for n in names:
        ops["textures"].pop(n, None)
        t = lock["textures"][n]
        shutil.copyfile(Path(root) / t["vanilla_png"], Path(root) / t["work_png"])
    save_ops(root, ops)
    return names


def changed(root: Path, lock: dict) -> list[str]:
    out = []
    for n, t in lock.get("textures", {}).items():
        w = Path(root) / t["work_png"]
        if w.is_file() and sha256_file(w) != t["png_sha256"]:
            out.append(n)
    return sorted(out)


def listing(root: Path, lock: dict) -> list[dict]:
    ops = load_ops(root)
    ch = set(changed(root, lock))
    out = []
    for n, t in sorted(lock.get("textures", {}).items()):
        k = kind_of(n)
        out.append({"name": n, "kind": k["kind"], "size": f"{t.get('width')}x{t.get('height')}", "format": t.get("format"),
                    "mips": t.get("mips"), "changed": n in ch, "ops": len(ops["textures"].get(n, {}).get("ops", [])),
                    "work_png": t["work_png"], "shared_from_other_skin": t.get("other_skin", False)})
    return out


def sheet(root: Path, lock: dict, names: list[str] | None = None, thumb: int = 512) -> dict:
    Image = _img()
    from PIL import ImageDraw
    names = names or changed(root, lock)
    if not names:
        raise ForgeError("NOTHING_CHANGED", "no texture differs from vanilla", "edit one first (mrforge tex hue ...)")
    pad, label = 8, 18
    w = 2 * thumb + 3 * pad
    h = len(names) * (thumb + label + pad) + pad
    canvas = Image.new("RGB", (w, h), (32, 32, 32))
    draw = ImageDraw.Draw(canvas)
    y = pad
    for n in names:
        t = lock["textures"][n]
        for col, rel_ in enumerate((t["vanilla_png"], t["work_png"])):
            im = Image.open(Path(root) / rel_).convert("RGBA")
            im.thumbnail((thumb, thumb))
            bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
            bg.alpha_composite(im)
            canvas.paste(bg.convert("RGB"), (pad + col * (thumb + pad), y + label))
        draw.text((pad, y + 2), f"{n}   vanilla | edited", fill=(230, 230, 230))
        y += thumb + label + pad
    out = Path(root) / "build" / "preview" / "sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return {"sheet": str(out), "textures": names, "size": [w, h]}
