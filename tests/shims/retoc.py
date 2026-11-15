"""Test shim for retoc-rivals-cli: info, manifest --filters, pack. Containers are JSON files."""
import base64
import json
import os
import sys
from pathlib import Path


def main(a):
    if a and a[0] in ("--version", "-V"):
        print("retoc-rivals-cli 3.11.1")
        return 0
    cmd = a[0] if a else ""
    if cmd == "info":
        p = Path(a[1])
        try:
            c = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            print("error: cannot read container", file=sys.stderr)
            return 1
        if p.suffix == ".pak":
            print(f"type: legacy-pak\nencrypted index: {'true' if c.get('encrypted_index') else 'false'}")
            return 0
        print(f"type: iostore\n{p.stem}\n  container_flags: EIoContainerFlags({' | '.join(c['flags'])})\n"
              f"  packages: {len(c['packages'])}")
        return 0
    if cmd == "manifest":
        p = Path(a[-1])
        c = json.load(open(p, encoding="utf-8"))
        for pkg in c["packages"]:
            print("../../../" + pkg)
        return 0
    if cmd == "pack":
        src = Path(a[1])
        out = Path(a[a.index("--output") + 1]) if "--output" in a else src.parent
        name = src.name + "_9999999_P"
        files: dict = {}
        for f in sorted(src.rglob("*")):
            if f.is_file():
                rel = f.relative_to(src).as_posix()
                stem = rel.rsplit(".", 1)[0]
                files.setdefault(stem + ".uasset", {})["." + rel.rsplit(".", 1)[1]] = base64.b64encode(f.read_bytes()).decode()
        flags = ["Compressed", "Indexed"] + (["Encrypted"] if os.environ.get("SHIM_ENCRYPT") else [])
        c = {"flags": flags, "packages": sorted(files), "files": files}
        out.mkdir(parents=True, exist_ok=True)
        (out / (name + ".utoc")).write_text(json.dumps(c, sort_keys=True), encoding="utf-8")
        (out / (name + ".ucas")).write_bytes(b"ucas" + json.dumps(sorted(files)).encode())
        (out / (name + ".pak")).write_bytes(b"pak")
        print(f"packed {name}")
        return 0
    print(f"shim: unsupported {a}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
