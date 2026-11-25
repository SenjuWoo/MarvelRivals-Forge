"""Test shim for UAssetTool: the subset mrforge uses, printing output in the real tool's format.

Vanilla content is described by <Paks>/fake_vanilla.json; mod containers are JSON .utoc files written by the
retoc shim. Textures are stored as PNG bytes in .uexp so the round trip can be checked for real.
"""
import base64
import io
import json
import os
import sys
from pathlib import Path


def png_bytes(w, h, color):
    from PIL import Image
    im = Image.new("RGBA", (w, h), tuple(color) + (255,))
    for x in range(w):
        im.putpixel((x, 0), (x * 7 % 256, 40, 200, 255))  # a little structure so hue shifts are visible
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        return args[i + 1]
    return default


def patterns(args):
    if "--filter" not in args:
        return []
    i = args.index("--filter") + 1
    out = []
    while i < len(args) and not args[i].startswith("--"):
        p = args[i]
        if p.endswith(".txt") and os.path.isfile(p):
            out += [ln.strip() for ln in open(p, encoding="utf-8") if ln.strip()]
        else:
            out.append(p)
        i += 1
    return out


def vanilla(paks):
    return json.load(open(Path(paks) / "fake_vanilla.json", encoding="utf-8"))["packages"]


def write_pkg(out_root, path, meta, files_b64=None):
    base = Path(out_root) / path
    base.parent.mkdir(parents=True, exist_ok=True)
    stem = base.with_suffix("")
    if files_b64:
        for ext, data in files_b64.items():
            stem.with_suffix(ext).write_bytes(base64.b64decode(data))
        return
    kind = meta["kind"]
    if kind == "texture":
        stem.with_suffix(".uasset").write_text(json.dumps({"kind": "texture", "fmt": meta["fmt"], "mips": meta["mips"],
                                                            "w": meta["w"], "h": meta["h"]}), encoding="utf-8")
        stem.with_suffix(".uexp").write_bytes(png_bytes(meta["w"], meta["h"], meta.get("color", [200, 120, 100])))
        stem.with_suffix(".ubulk").write_bytes(b"bulk")
    elif kind in ("material", "json"):
        stem.with_suffix(".uasset").write_text(json.dumps({"kind": "material"}), encoding="utf-8")
        stem.with_suffix(".uexp").write_text(json.dumps(meta["json"]), encoding="utf-8")
    else:
        stem.with_suffix(".uasset").write_text(json.dumps({"kind": kind}), encoding="utf-8")


def main(a):
    cmd = a[0] if a else ""
    if cmd == "version":
        print("UAssetTool v1.5.9+shim")
        return 0
    if cmd == "list_iostore":
        paks, filt = a[1], opt(a, "--filter", "")
        print("=== pakchunkCharacter-Windows.utoc ===")
        for p, meta in sorted(vanilla(paks).items()):
            if filt in p:
                print(f"  ../../../{p} [{'.ubulk' if meta['kind'] == 'texture' else 'no bulk'}]  (export=1,234b)")
        return 0
    if cmd == "extract_iostore_legacy":
        paks, out = a[1], a[2]
        pats = patterns(a)
        mod = opt(a, "--mod")
        n = 0
        if mod:
            c = json.load(open(mod, encoding="utf-8"))
            for p, files in c["files"].items():
                if any(x in p for x in pats):
                    write_pkg(out, p, None, files)
                    n += 1
        else:
            for p, meta in vanilla(paks).items():
                if any(x in p for x in pats):
                    write_pkg(out, p, meta)
                    n += 1
        print(f"Extraction complete: {n} converted, 0 failed, 0 skipped")
        return 0
    if cmd in ("batch_extract_texture", "extract_texture"):
        if cmd == "extract_texture":
            items = [(Path(a[1]), Path(a[2]))]
        else:
            src, dst = Path(a[1]), Path(a[2])
            items = [(u, dst / u.relative_to(src).with_suffix(".png")) for u in sorted(src.rglob("*.uasset"))]
        ok = 0
        for u, png in items:
            meta = json.loads(u.read_text(encoding="utf-8"))
            rel = str(u).replace("/", "\\")
            if meta.get("kind") != "texture":
                print(f"  {rel} ... SKIP: No Texture2D export found in asset.")
                continue
            data = u.with_suffix(".uexp").read_bytes()
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(data)
            from PIL import Image
            w, h = Image.open(png).size
            if cmd == "batch_extract_texture":
                relp = str(u.relative_to(Path(a[1]))).replace("/", "\\")
                print(f"  {relp} ...   Texture: {w}x{h}, format={meta['fmt']}")
                print(f"  Mip count: {meta['mips']}")
                print(f"  Saved: {png}")
                print(f"OK ({w}x{h}, {meta['fmt']})")
            else:
                print(f"  Texture: {w}x{h}, format={meta['fmt']}\n  Mip count: {meta['mips']}\n\nSuccess!\n"
                      f"  Dimensions: {w}x{h}\n  Mip Count: {meta['mips']}\n  Pixel Format: {meta['fmt']}")
            ok += 1
        if cmd == "batch_extract_texture":
            print(f"\nBatch extract complete: {ok} succeeded, 0 errors")
        return 0
    if cmd == "inject_texture":
        base, png, out = Path(a[1]), Path(a[2]), Path(a[3])
        meta = json.loads(base.read_text(encoding="utf-8"))
        from PIL import Image
        w, h = Image.open(png).size
        meta.update(w=w, h=h)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(meta), encoding="utf-8")
        out.with_suffix(".uexp").write_bytes(png.read_bytes())
        out.with_suffix(".ubulk").write_bytes(b"bulk")
        out.with_suffix(".uptnl").write_bytes(b"tnl")
        print("Injected")
        return 0
    if cmd == "to_json":
        src, outdir = Path(a[1]), Path(a[3])
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / (src.stem + ".json")).write_text(src.with_suffix(".uexp").read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Asset exported to JSON: {outdir / (src.stem + '.json')}")
        return 0
    if cmd == "from_json":
        js, out = Path(a[1]), Path(a[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"kind": "material"}), encoding="utf-8")
        out.with_suffix(".uexp").write_text(js.read_text(encoding="utf-8"), encoding="utf-8")
        print("Asset imported from JSON")
        return 0
    if cmd == "skeletal_mesh_info":
        print("=== Skeletal Mesh Analysis ===\n\n  === Materials (2) ===\n    [0] MaterialInterface: -1\n        SlotName: MI_A\n"
              "        ImportedSlotName: 01 - Default\n        GameplayTags: 1\n          - MaterialTag.X\n"
              "    [1] MaterialInterface: -2\n        SlotName: MI_B\n        ImportedSlotName: 01 - Default\n        GameplayTags: 0\n")
        return 0
    print(f"shim: unsupported {a}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
