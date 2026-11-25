"""Sound route (v1.2): replace a skin's sounds with your own audio. No Wwise, no Unreal (decision D31).

How the game stores sound: Wwise sound banks (.bnk) and streamed media (.wem) are loose files in the legacy pak
`pakchunkWwise-Windows.pak` (mount Marvel/Content/WwiseAudio/), newer copies in the `Patch_*` pak. Each skin has its
own `bnk_sfx_<skin>.bnk` (abilities, weapons) and `bnk_display_<skin>.bnk` (hero select / MVP). A bank holds HIRC
(events, actions, containers, Sound objects; each Sound names one media id) and DIDX/DATA (the embedded media).

The route, the one community sound mods ship (Rivals-Toolkit's sound builder, repak-xtra's Sounds tab):
- the replacement is written as a Wwise PCM .wem (16-bit stereo, the RIFF layout below) and put in place of the
  vanilla media in DIDX/DATA. HIRC stays byte-identical: pointing a Sound object at a new media id crashed the game
  (reported by repak-xtra, 2026-11-17), and the game plays PCM media under the bank's Vorbis entries.
- a streamed Sound (stream type != 0) also gets the file at Media/[<language>/]<first two digits>/<id>.wem.
- the bank goes into the mod's companion pak at Marvel/Content/WwiseAudio/<bank>; since the game's September 2026
  update it loads one copy of a bank, so two mods carrying the same bank conflict (V-CONFLICT names them).

Event names come from the WwiseEvents packages in the package index: a Wwise event id is the FNV-1 hash of its
lower-case name. Containers are matched to their children by the parent id each child carries.
"""
from __future__ import annotations

import fnmatch
import shutil
import struct
import tempfile
import wave
from pathlib import Path

from .util import ForgeError, UsageError, fwd, iter_files, load_json, run, save_json, sha256_bytes, sha256_file

WWISE = "Marvel/Content/WwiseAudio/"
WWISE_PAK = "pakchunkWwise-Windows.pak"
MAX_SECONDS = 30  # bank media sit in memory (about 190 KB per second of 48 kHz stereo PCM)
RATE = 48000
SILENCE_FRAMES = 480  # 10 ms: what a stacked layer plays instead of a second copy of the new sound
PLAY = 0x0403  # HIRC action type: Play
RANDOM = 5  # HIRC type: random/sequence container (variations)
CONTAINERS = {5, 6, 7, 9}  # random/sequence, switch, actor-mixer, layer

# Wwise PCM .wem header up to the data chunk (96 bytes): WAVE_FORMAT_EXTENSIBLE stereo 16-bit fmt chunk, a "hash"
# chunk and two junk chunks, as in a PCM .wem the game ships. Taken from oZanderr/Rivals-Toolkit
# (src-tauri/src/audio/wem.rs, MIT or Apache-2.0; notice in THIRD-PARTY.md). RIFF size, sample rate and bytes per
# second are filled in per sound; the RIFF size is 80 + data length, as the files that toolkit ships and the game plays.
WEM_HEADER = bytes([
    0x52, 0x49, 0x46, 0x46, 0x00, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
    0x66, 0x6D, 0x74, 0x20, 0x18, 0x00, 0x00, 0x00, 0xFE, 0xFF, 0x02, 0x00,
    0x80, 0xBB, 0x00, 0x00, 0x00, 0x77, 0x01, 0x00, 0x04, 0x00, 0x10, 0x00,
    0x06, 0x00, 0x00, 0x00, 0x02, 0x31, 0x00, 0x00,
    0x68, 0x61, 0x73, 0x68, 0x10, 0x00, 0x00, 0x00, 0x46, 0x26, 0xE0, 0xBF, 0x91, 0x29, 0x78, 0xDD,
    0x78, 0x67, 0x99, 0x9C, 0xA4, 0x66, 0xBA, 0x21,
    0x6A, 0x75, 0x6E, 0x6B, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x4A, 0x55, 0x4E, 0x4B, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


# ---------------------------------------------------------------------------------------------------- bank format

def fnv1(name: str) -> int:
    """Wwise short id of a name: 32-bit FNV-1 of the lower-case UTF-8 bytes."""
    h = 2166136261
    for c in name.lower().encode("utf-8"):
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= c
    return h


def sections(b: bytes) -> list[tuple[bytes, int, int]]:
    """(tag, body start, body end) of every section; the walk must end exactly at the end of the file."""
    out, o = [], 0
    while o + 8 <= len(b):
        tag, size = b[o:o + 4], struct.unpack_from("<I", b, o + 4)[0]
        if o + 8 + size > len(b):
            raise ForgeError("BANK_UNREADABLE", f"section {tag!r} runs past the end of the bank")
        out.append((tag, o + 8, o + 8 + size))
        o += 8 + size
    if o != len(b) or not out or out[0][0] != b"BKHD":
        raise ForgeError("BANK_UNREADABLE", "not a Wwise sound bank (no BKHD, or bytes after the last section)")
    return out


def _sec(b: bytes, tag: bytes) -> tuple[int, int] | None:
    return next(((s, e) for t, s, e in sections(b) if t == tag), None)


def media(b: bytes) -> list[tuple[int, int, int]]:
    """(media id, offset into DATA, size) in DIDX order."""
    d = _sec(b, b"DIDX")
    if not d:
        return []
    return [struct.unpack_from("<III", b, i) for i in range(d[0], d[1], 12)]


def media_bytes(b: bytes) -> dict[int, bytes]:
    data = _sec(b, b"DATA")
    return {mid: b[data[0] + off:data[0] + off + size] for mid, off, size in media(b)} if data else {}


def hirc(b: bytes) -> dict[int, tuple[int, bytes]]:
    """HIRC objects: id -> (type, body after the id)."""
    h = _sec(b, b"HIRC")
    if not h:
        return {}
    count, p, out = struct.unpack_from("<I", b, h[0])[0], h[0] + 4, {}
    for _ in range(count):
        t, size, oid = b[p], *struct.unpack_from("<II", b, p + 1)
        out[oid] = (t, b[p + 9:p + 5 + size])
        p += 5 + size
    if p != h[1]:
        raise ForgeError("BANK_UNREADABLE", "the HIRC walk did not end on the section end")
    return out


def sound_objects(b: bytes) -> dict[int, dict]:
    """Sound objects (HIRC type 2): id -> source media id, stream type, codec plugin id."""
    out = {}
    for oid, (t, body) in hirc(b).items():
        if t == 2 and len(body) >= 13:
            plugin, stream, src = struct.unpack_from("<IBI", body, 0)
            out[oid] = {"source": src, "stream": stream, "plugin": plugin}
    return out


def alignment(b: bytes) -> int:
    """The largest power of two that reproduces every vanilla DIDX offset."""
    ents = media(b)
    if len(ents) < 2:
        return 16
    best = 1
    for a in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
        cur, ok = 0, True
        for _, off, size in ents:
            if -(-cur // a) * a != off:
                ok = False
                break
            cur = off + size
        if ok:
            best = a
    return best


def rebuild(game: bytes, repl: dict[int, bytes]) -> bytes:
    """The game's bank with media replaced in place (same ids, same DIDX order). Every other section is copied byte
    for byte; with no replacements the result equals the input."""
    ents = media(game)
    have = {mid for mid, _, _ in ents}
    missing = sorted(set(repl) - have)
    if missing:
        raise ForgeError("SOUND_MEDIA_UNKNOWN", f"media {missing[:5]} are not in this bank", "mrforge sound list")
    old = media_bytes(game)
    align = alignment(game)
    data, didx = bytearray(), bytearray()
    old_data = _sec(game, b"DATA")
    for mid, _, _ in ents:
        blob = repl.get(mid, old[mid])
        data += b"\0" * (-(-len(data) // align) * align - len(data))
        didx += struct.pack("<III", mid, len(data), len(blob))
        data += blob
    if old_data and ents:
        # vanilla keeps padding after the last media too: same length, so an unedited rebuild is byte-identical
        _, off, size = ents[-1]
        data += b"\0" * max(0, (old_data[1] - old_data[0]) - (off + size))
    out = bytearray()
    for tag, s, e in sections(game):
        body = bytes(didx) if tag == b"DIDX" else bytes(data) if tag == b"DATA" else game[s:e]
        out += tag + struct.pack("<I", len(body)) + body
    return bytes(out)


def readback(game: bytes, built: bytes, repl: dict[int, bytes]) -> list[str]:
    """Problems with a built bank against the game's: HIRC changed, a replaced media not equal to its .wem, an untouched
    media not equal to vanilla, a media id added or lost."""
    probs = []
    try:
        g_sec = {t: game[s:e] for t, s, e in sections(game)}
        b_sec = {t: built[s:e] for t, s, e in sections(built)}
    except ForgeError as e:
        return [e.message]
    if g_sec.get(b"HIRC") != b_sec.get(b"HIRC"):
        probs.append("HIRC differs from the game's bank")
    for t in g_sec:
        if t not in (b"DIDX", b"DATA") and g_sec[t] != b_sec.get(t):
            probs.append(f"section {t.decode(errors='replace')} differs")
    gm, bm = media_bytes(game), media_bytes(built)
    if set(gm) != set(bm):
        probs.append(f"media ids differ (+{sorted(set(bm) - set(gm))[:3]} -{sorted(set(gm) - set(bm))[:3]})")
    for mid, blob in bm.items():
        want = repl.get(mid, gm.get(mid))
        if blob != want:
            probs.append(f"media {mid} " + ("is not the replacement" if mid in repl else "changed but was not edited"))
    return probs


def wem_info(blob: bytes) -> dict:
    if blob[:4] != b"RIFF" or len(blob) < 32:
        return {"codec": None}
    tag, ch, rate = struct.unpack_from("<HHI", blob, 20)
    codec = {0xFFFF: "vorbis", 0x3041: "opus", 0xFFFE: "pcm", 0x0001: "pcm", 0x0002: "adpcm"}.get(tag, hex(tag))
    return {"codec": codec, "channels": ch, "rate": rate}


def encode_wem(pcm: bytes, rate: int, channels: int) -> bytes:
    """16-bit interleaved PCM -> Wwise PCM .wem (always stereo; mono is written to both channels)."""
    if channels not in (1, 2):
        raise UsageError("mono or stereo audio only")
    if channels == 1:
        frames = struct.unpack(f"<{len(pcm) // 2}h", pcm[:len(pcm) // 2 * 2])
        pcm = struct.pack(f"<{2 * len(frames)}h", *(s for f in frames for s in (f, f)))
    pcm = pcm[:len(pcm) // 4 * 4]
    if not pcm:
        raise UsageError("the sound is empty")
    h = bytearray(WEM_HEADER)
    struct.pack_into("<I", h, 4, 80 + len(pcm))
    struct.pack_into("<II", h, 24, rate, rate * 4)
    return bytes(h) + b"data" + struct.pack("<I", len(pcm)) + pcm


def silence() -> bytes:
    return encode_wem(b"\0\0" * SILENCE_FRAMES, RATE, 1)


def read_wav(path: Path) -> tuple[bytes, int, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() not in (1, 2):
            raise UsageError(f"{path.name}: not a 16-bit mono/stereo WAV")
        return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()


# ---------------------------------------------------------------------------------------------------- events

def event_map(b: bytes, names: list[str] | None = None) -> dict[str, dict]:
    """Event name (or id when the name is unknown) -> media ids, split into the primary Play target (the one with the
    most variations) and the other targets that play at the same time (layers)."""
    objs = hirc(b)
    sounds = {oid: v for oid, v in sound_objects(b).items()}
    parents: dict[int, list[int]] = {}
    for oid, (t, body) in objs.items():
        if t in (2, 5, 6, 9):
            ids = {struct.unpack_from("<I", body, i)[0] for i in range(0, len(body) - 3)}
            parents[oid] = [x for x in ids if x != oid and x in objs and objs[x][0] in CONTAINERS]

    def under(oid: int, target: int, seen: frozenset = frozenset()) -> bool:
        return oid == target or any(under(p, target, seen | {oid}) for p in parents.get(oid, []) if p not in seen)

    byhash = {fnv1(n): n for n in (names or [])}
    out = {}
    for eid, (t, body) in objs.items():
        if t != 4:
            continue
        ids = {struct.unpack_from("<I", body, i)[0] for i in range(0, len(body) - 3)}
        targets = []
        for a in sorted(x for x in ids if x in objs and objs[x][0] == 3):
            ab = objs[a][1]
            if len(ab) >= 6 and struct.unpack_from("<H", ab, 0)[0] == PLAY:
                tgt = struct.unpack_from("<I", ab, 2)[0]
                med = sorted({sounds[s]["source"] for s in sounds if under(s, tgt)})
                if med:
                    targets.append({"target": tgt, "type": objs.get(tgt, (None,))[0], "media": med})
        if not targets:
            continue
        targets.sort(key=lambda x: (-len(x["media"]), x["target"]))
        out[byhash.get(eid, str(eid))] = {"id": eid, "primary": targets[0]["media"],
                                          "variations": targets[0]["type"] == RANDOM,
                                          "layers": sorted({m for x in targets[1:] for m in x["media"]} - set(targets[0]["media"]))}
    return out


# ---------------------------------------------------------------------------------------------------- game files

def _key() -> str:
    from .sync import aes_key
    k = aes_key()
    if not k:
        raise ForgeError("AES_KEY_MISSING", "the game's AES key is not cached", "mrforge sync")
    return k.removeprefix("0x")


def _list(pak: Path) -> tuple[str, list[str]]:
    from .tools import run_tool
    r = run_tool("uassettool", ["list_pak", fwd(pak), "--aes", _key()], timeout=600)
    if r["rc"] != 0:
        raise ForgeError("PAK_LIST_FAILED", f"{pak.name}: {(r['stdout'] + r['stderr']).strip()[-300:]}", "mrforge doctor")
    mount, entries = "", []
    for ln in r["stdout"].splitlines():
        s = ln.strip()
        if s.startswith("Mount Point:"):
            mount = s.split(":", 1)[1].strip()
        elif ln.startswith("  ") and not ln.startswith("   ") and s and ": " not in s and not s.startswith("Total"):
            entries.append(s)
    return mount, entries


def full_path(mount: str, entry: str) -> str:
    m = mount.replace("\\", "/")
    while m.startswith("../"):
        m = m[3:]
    return (m.rstrip("/") + "/" + entry.lstrip("/")).lstrip("/") if m else entry.lstrip("/")


def game_files(paks_dir: Path) -> dict[str, tuple[Path, str, str]]:
    """Sound files of the game by lower-case path under WwiseAudio -> (pak, entry, real path). Patch paks win over
    the base pak (highest patch first), as in the game's own pak order."""
    paks = sorted(Path(paks_dir).glob("Patch_*.pak"), key=lambda p: p.name, reverse=True) + [Path(paks_dir) / WWISE_PAK]
    out: dict = {}
    for pak in paks:
        if not pak.is_file():
            continue
        mount, entries = _list(pak)
        for e in entries:
            fp = full_path(mount, e)
            if fp.lower().startswith(WWISE.lower()) and fp.lower().endswith((".bnk", ".wem")):
                out.setdefault(fp[len(WWISE):].lower(), (pak, e, fp))
    return out


def extract(pak: Path, entry: str, dest: Path) -> bytes:
    from .tools import run_tool
    tmp = Path(tempfile.mkdtemp(prefix="mrf-snd-"))
    try:
        name = entry.replace("\\", "/").rsplit("/", 1)[-1]
        r = run_tool("uassettool", ["extract_pak", fwd(pak), fwd(tmp), "--aes", _key(), "--filter", name], timeout=600)
        want = entry.replace("\\", "/").lstrip("/").lower()
        hit = next((f for f in iter_files(tmp) if f.relative_to(tmp).as_posix().lower().endswith(want)), None)
        if r["rc"] != 0 or not hit:
            raise ForgeError("PAK_EXTRACT_FAILED", f"{entry} from {pak.name}: {(r['stdout'] + r['stderr']).strip()[-300:]}",
                             "mrforge doctor; mrforge sync (AES key)")
        data = hit.read_bytes()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def media_path(bank_rel: str, mid: int) -> str:
    """Streamed media path under WwiseAudio for a bank (language banks stream from Media/<language>/)."""
    lang = bank_rel.rsplit("/", 1)[0] + "/" if "/" in bank_rel else ""
    return f"Media/{lang}{str(mid)[:2]}/{mid}.wem"


# ---------------------------------------------------------------------------------------------------- project state

def state_path(root: Path) -> Path:
    return Path(root) / "work" / "sounds" / "sounds.json"


def ops_path(root: Path) -> Path:
    return Path(root) / "work" / "sounds" / "ops.json"


def load_state(root: Path, required: bool = True) -> dict:
    s = load_json(state_path(root), {})
    if required and not s.get("banks"):
        raise ForgeError("SOUNDS_NOT_EXTRACTED", "no sound banks extracted in this project", "mrforge extract --sounds")
    return s


def load_ops(root: Path) -> dict:
    return load_json(ops_path(root), {"replace": {}})


def default_banks(skin_id: str) -> list[str]:
    return [f"bnk_sfx_{skin_id}.bnk", f"bnk_display_{skin_id}.bnk"]


def event_names(changelist: int, skin_id: str | None = None) -> list[str]:
    from . import index as I
    idx = I.load(changelist, required=False) or {"packages": {}}
    return sorted({Path(p).stem for p in idx["packages"] if "/wwise" in p.lower()})


def extract_banks(root: Path, groot: Path, changelist: int, skin_id: str, banks: list[str] | None = None) -> dict:
    from .game import layout
    files = game_files(layout(groot)["paks_dir"])
    names = event_names(changelist)
    st = load_state(root, required=False)
    st.update(changelist=changelist)
    st.setdefault("banks", {})
    done, warns = [], []
    for want in banks or default_banks(skin_id):
        rel = want if want.lower().endswith(".bnk") else want + ".bnk"
        hit = files.get(rel.lower()) or next((v for k, v in files.items() if k.endswith("/" + rel.lower())), None)
        if not hit:
            warns.append(f"{rel}: not in the game's sound paks")
            continue
        pak, entry, fp = hit
        real_rel = fp[len(WWISE):]
        dest = Path(root) / "vanilla" / "sounds" / real_rel
        data = extract(pak, entry, dest)
        sounds = sound_objects(data)
        mb = media_bytes(data)
        evs = event_map(data, names)
        users: dict[int, list[str]] = {}
        for n, e in evs.items():
            for mid in e["primary"] + e["layers"]:
                users.setdefault(mid, []).append(n)
        info = {}
        for s in sounds.values():
            mid = s["source"]
            if mid in mb or s["stream"]:
                w = wem_info(mb.get(mid, b""))
                info[str(mid)] = {"size": len(mb.get(mid, b"")), "stream": s["stream"], "in_bank": mid in mb,
                                  "codec": w.get("codec"), "events": sorted(set(users.get(mid, [])))}
        st["banks"][real_rel] = {"path": fp, "source_pak": pak.name, "vanilla": f"vanilla/sounds/{real_rel}",
                                 "sha256": sha256_bytes(data), "events": evs, "media": info}
        if "/" in real_rel and real_rel.rsplit("/", 1)[1].startswith("bnk_vo_"):
            warns.append(f"{real_rel}: hero voice bank, shared by every skin of the hero")
        done.append({"bank": real_rel, "from": pak.name, "events": len(evs), "media": len(info),
                     "named_events": sum(1 for n in evs if not n.isdigit())})
    save_json(state_path(root), st)
    return {"banks": done, "warnings": warns}


def listing(root: Path, pattern: str | None = None) -> list[dict]:
    st = load_state(root)
    ops = load_ops(root)["replace"]
    out = []
    for rel, b in st["banks"].items():
        for name, e in sorted(b["events"].items()):
            if pattern and not fnmatch.fnmatch(name.lower(), pattern.lower()):
                continue
            done = [m for m in e["primary"] + e["layers"] if str(m) in ops.get(rel, {})]
            out.append({"bank": rel, "event": name, "variations": len(e["primary"]) if e["variations"] else 1,
                        "primary": e["primary"], "layers": e["layers"], "replaced": done})
    return out


def find_event(st: dict, name: str) -> tuple[str, str, dict]:
    hits = [(rel, n, e) for rel, b in st["banks"].items() for n, e in b["events"].items()
            if n.lower() == name.lower() or str(e["id"]) == name]
    if not hits:
        hits = [(rel, n, e) for rel, b in st["banks"].items() for n, e in b["events"].items()
                if fnmatch.fnmatch(n.lower(), name.lower())]
    if not hits:
        raise ForgeError("SOUND_EVENT_UNKNOWN", f"no event {name!r} in the extracted banks", "mrforge sound list")
    if len(hits) > 1:
        raise UsageError(f"{name!r} matches {len(hits)} events: {[h[1] for h in hits[:6]]}", "give the exact event name")
    return hits[0]


def convert(src: Path, dest: Path, gain_db: float = 0.0, max_seconds: int = MAX_SECONDS) -> dict:
    """Any audio ffmpeg reads -> 48 kHz 16-bit stereo WAV. A 16-bit PCM WAV within the length cap is taken as it is
    (no ffmpeg needed)."""
    if not Path(src).is_file():
        raise UsageError(f"no such file: {src}")
    if Path(src).suffix.lower() == ".wav" and not gain_db:
        try:
            pcm, rate, ch = read_wav(Path(src))
        except (UsageError, wave.Error, EOFError):
            pcm = None
        if pcm and len(pcm) / (rate * ch * 2) <= max_seconds and 8000 <= rate <= 192000:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            return {"seconds": round(len(pcm) / (rate * ch * 2), 3), "rate": rate, "channels": ch}
    ff = shutil.which("ffmpeg")
    if not ff:
        raise ForgeError("FFMPEG_MISSING", "ffmpeg is not on PATH (needed for anything but a 16-bit WAV)",
                         "install ffmpeg (winget install Gyan.FFmpeg), or give a 16-bit PCM .wav")
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = [ff, "-y", "-v", "error", "-i", str(src), "-t", str(max_seconds), "-ac", "2", "-ar", str(RATE), "-c:a", "pcm_s16le"]
    if gain_db:
        argv += ["-af", f"volume={gain_db}dB"]
    r = run(argv + [str(dest)], timeout=300)
    if r["rc"] != 0 or not dest.is_file():
        raise ForgeError("AUDIO_CONVERT_FAILED", (r["stdout"] + r["stderr"]).strip()[-300:], "check the file plays")
    pcm, rate, ch = read_wav(dest)
    return {"seconds": round(len(pcm) / (rate * ch * 2), 3), "rate": rate, "channels": ch}


def replace(root: Path, target: str, src: Path, media_id: int | None = None, keep_layers: bool = False,
            gain_db: float = 0.0) -> dict:
    """Record a replacement: every variation of the event's primary Play target gets the new sound; the event's
    other layers get 10 ms of silence (so the sound plays once) unless keep_layers."""
    st = load_state(root)
    if media_id is not None:
        rel = next((r for r, b in st["banks"].items() if str(media_id) in b["media"]), None)
        if not rel:
            raise ForgeError("SOUND_MEDIA_UNKNOWN", f"media {media_id} is not in the extracted banks", "mrforge sound list")
        primary, layers, label = [media_id], [], str(media_id)
    else:
        rel, label, e = find_event(st, target)
        primary, layers = e["primary"], ([] if keep_layers else e["layers"])
    stem = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)[:80]
    wav = Path(root) / "work" / "sounds" / "audio" / f"{stem}.wav"
    info = convert(Path(src), wav, gain_db)
    ops = load_ops(root)
    bank_ops = ops["replace"].setdefault(rel, {})
    rec = {"file": f"work/sounds/audio/{stem}.wav", "sha256": sha256_file(wav), "for": label, "source": Path(src).name}
    for m in primary:
        bank_ops[str(m)] = dict(rec)
    for m in layers:
        if str(m) not in bank_ops or bank_ops[str(m)].get("silence"):
            bank_ops[str(m)] = {"silence": True, "for": label}
    save_json(ops_path(root), ops)
    media = st["banks"][rel]["media"]
    shared = sorted({ev for m in primary + layers for ev in media.get(str(m), {}).get("events", []) if ev != label})
    return {"bank": rel, "event": label, "replaced": primary, "silenced": layers, "audio": info, "shared_with": shared}


def reset(root: Path, target: str | None = None) -> list[str]:
    ops = load_ops(root)
    if not target:
        gone = [f"{r}:{m}" for r, b in ops["replace"].items() for m in b]
        ops["replace"] = {}
    else:
        gone = []
        for r, b in ops["replace"].items():
            for m in [m for m, v in b.items() if v.get("for", "").lower() == target.lower() or m == target]:
                gone.append(f"{r}:{m}")
                del b[m]
        ops["replace"] = {r: b for r, b in ops["replace"].items() if b}
    save_json(ops_path(root), ops)
    return gone


def changed(root: Path) -> list[str]:
    return sorted(r for r, b in load_ops(root)["replace"].items() if b)


def replacements(root: Path, rel: str) -> dict[int, bytes]:
    ops = load_ops(root)["replace"].get(rel, {})
    out, cache, quiet = {}, {}, silence()
    for mid, v in ops.items():
        if v.get("silence"):
            out[int(mid)] = quiet
            continue
        f = Path(root) / v["file"]
        if not f.is_file() or sha256_file(f) != v["sha256"]:
            raise ForgeError("SOUND_AUDIO_CHANGED", f"{v['file']} is missing or changed since sound replace",
                             f"mrforge sound replace {v['for']} <file> again")
        if v["file"] not in cache:
            cache[v["file"]] = encode_wem(*read_wav(f))
        out[int(mid)] = cache[v["file"]]
    return out


def stage(root: Path, stage_dir: Path) -> dict:
    """Write every edited bank (and its streamed media) under stage_dir/Marvel/Content/WwiseAudio; read each back."""
    st = load_state(root)
    done = {}
    for rel in changed(root):
        b = st["banks"].get(rel)
        if not b:
            raise ForgeError("SOUNDS_NOT_EXTRACTED", f"{rel} has edits but is not extracted", "mrforge extract --sounds")
        game = (Path(root) / b["vanilla"]).read_bytes()
        if sha256_bytes(game) != b["sha256"]:
            raise ForgeError("SOUND_VANILLA_CHANGED", f"{b['vanilla']} differs from the extracted bank", "mrforge extract --sounds")
        repl = replacements(root, rel)
        built = rebuild(game, {m: w for m, w in repl.items() if m in media_bytes(game)})
        probs = readback(game, built, {m: w for m, w in repl.items() if m in media_bytes(game)})
        if probs:
            raise ForgeError("SOUND_READBACK_FAILED", f"{rel}: {'; '.join(probs[:5])}", "report this bank")
        out = Path(stage_dir) / (WWISE + rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(built)
        streamed = []
        for mid, w in repl.items():
            if b["media"].get(str(mid), {}).get("stream"):
                p = Path(stage_dir) / (WWISE + media_path(rel, mid))
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(w)
                streamed.append(media_path(rel, mid))
        done[rel] = {"path": WWISE + rel, "replaced": sorted(m for m, w in repl.items() if w != silence()),
                     "silenced": sorted(m for m, w in repl.items() if w == silence()), "streamed": streamed,
                     "vanilla_sha256": b["sha256"], "built_sha256": sha256_bytes(built)}
    return done


def verify_pak(root: Path, pak: Path) -> list[str]:
    """V-SND: every edited bank read back out of the built pak against the game's and the edits."""
    st = load_state(root)
    mount, entries = _list(pak)
    have = {full_path(mount, e).lower(): e for e in entries}
    probs = []
    for rel in changed(root):
        b = st["banks"][rel]
        e = have.get((WWISE + rel).lower())
        if not e:
            probs.append(f"{rel}: not in {pak.name}")
            continue
        tmp = Path(tempfile.mkdtemp(prefix="mrf-vsnd-"))
        try:
            built = extract(pak, e, tmp / "bank.bnk")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        game = (Path(root) / b["vanilla"]).read_bytes()
        repl = {m: w for m, w in replacements(root, rel).items() if m in media_bytes(game)}
        probs += [f"{rel}: {p}" for p in readback(game, built, repl)]
        for mid in replacements(root, rel):
            if b["media"].get(str(mid), {}).get("stream") and (WWISE + media_path(rel, mid)).lower() not in have:
                probs.append(f"{rel}: streamed media {mid} missing from the pak")
    return probs


def mod_banks(pak: Path) -> list[str]:
    """Sound files (paths under WwiseAudio, lower case) a mod's .pak carries; [] when it cannot be listed."""
    try:
        mount, entries = _list(pak)
    except ForgeError:
        return []
    return sorted(fp[len(WWISE):].lower() for fp in (full_path(mount, e) for e in entries)
                  if fp.lower().startswith(WWISE.lower()) and fp.lower().endswith((".bnk", ".wem")))
