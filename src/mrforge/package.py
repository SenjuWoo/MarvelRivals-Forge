"""mrforge package: deterministic zip holding only the triple (plus README.txt when described)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from . import project as P
from .build import built_files
from .util import ForgeError, sha256_file

FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def run(root: Path) -> dict:
    root = Path(root)
    m = P.manifest(root)
    tr = built_files(root, m)
    missing = [p.name for p in tr.values() if not p.is_file()]
    if missing:
        raise ForgeError("NOT_BUILT", f"missing {missing}", "mrforge build && mrforge validate")
    entries: list[tuple[str, bytes]] = []
    for p in tr.values():
        # Inside the zip the triple sits in a folder named like the mod, so a mod manager keeps it together.
        entries.append((f"{m['pak_name']}/{p.name}", p.read_bytes()))
    if m.get("description"):
        text = f"{m['name']} {m['version']}\nSkin: {m['skin_id']} {m.get('hero', '')} {m.get('skin', '')}\n\n{m['description']}\n"
        entries.append((f"{m['pak_name']}/README.txt", text.replace("\r\n", "\n").encode("utf-8")))
    entries.sort(key=lambda e: e[0])
    out = root / "dist" / f"{m['pak_name']}-{m['version']}.zip"
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            zi.compress_type = zipfile.ZIP_STORED  # identical bytes on every OS; the containers are already Oodle-compressed
            zi.external_attr = 0o644 << 16
            zi.create_system = 0
            zf.writestr(zi, data)
    tmp.replace(out)
    return {"zip": str(out), "sha256": sha256_file(out), "entries": [e[0] for e in entries],
            "size": out.stat().st_size}
