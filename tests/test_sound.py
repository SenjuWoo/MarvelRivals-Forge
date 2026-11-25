"""Sound route: bank rebuild, event map, PCM .wem, and the extract -> replace -> build -> validate -> deploy loop."""
import base64
import json
import struct
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import SKIN, ForgeCase  # noqa: E402

from mrforge import snd as SN  # noqa: E402
from mrforge.util import ForgeError, UsageError  # noqa: E402

EVENT = f"sfx_{SKIN}_left_release_play"


def vorbis(n: int, tag: int = 0xFFFF) -> bytes:
    body = struct.pack("<HHI", tag, 2, 48000) + b"\0" * 8 + bytes([n % 251]) * (n * 37 % 300 + 40)
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVEfmt " + body


def bank(stream_media: int | None = None, display: bool = False) -> bytes:
    """One event (EVENT) playing a random container with two variations plus a direct layer sound; a second event
    sharing the layer's media; a streamed sound when stream_media is given (display=True: only that sound and its
    event, as in a display bank)."""
    objs = []

    def sound(sid, src, parent, stream=0):
        body = struct.pack("<IBII", 0x40001, stream, src, 100) + b"\0" * 6 + struct.pack("<I", parent) + b"\0" * 4
        objs.append((2, sid, body))

    objs.append((7, 700, b"\0" * 12))  # actor-mixer
    if not display:
        objs.append((5, 900, b"\0" * 5 + struct.pack("<I", 700) + b"\0" * 7))  # random container under the mixer
        sound(10, 1001, 900)
        sound(11, 1002, 900)
        sound(12, 1003, 700)
    if stream_media:
        sound(13, stream_media, 700, stream=1)

    def event(name, targets):
        acts = []
        for i, t in enumerate(targets):
            aid = SN.fnv1(name) ^ (i + 1)
            objs.append((3, aid, struct.pack("<HI", SN.PLAY, t) + b"\0" * 6))
            acts.append(aid)
        objs.append((4, SN.fnv1(name), bytes([len(acts)]) + b"".join(struct.pack("<I", a) for a in acts)))

    if not display:
        event(EVENT, [900, 12])
        event(f"sfx_{SKIN}_q_release_play", [12])
    if stream_media:
        event(f"display_{SKIN}_mvp_play", [13])
    hirc = struct.pack("<I", len(objs)) + b"".join(bytes([t]) + struct.pack("<II", len(b) + 4, oid) + b
                                                   for t, oid, b in objs)
    didx, data = b"", b""
    for mid in (() if display else (1001, 1002, 1003)) + ((stream_media,) if stream_media else ()):
        data += b"\0" * (-len(data) % 16)
        m = vorbis(mid)
        didx += struct.pack("<III", mid, len(data), len(m))
        data += m
    data += b"\0" * 5  # vanilla banks pad after the last media too
    out = b""
    for tag, body in ((b"BKHD", b"\x91\0\0\0" + b"\0" * 12), (b"DIDX", didx), (b"DATA", data), (b"HIRC", hirc)):
        out += tag + struct.pack("<I", len(body)) + body
    return out


def wav(path: Path, seconds=0.25, ch=1, rate=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{int(rate * seconds) * ch}h", *([1200, -1200] * (int(rate * seconds) * ch // 2))))
    return path


class BankFormat(unittest.TestCase):
    def test_fnv1_matches_the_game(self):
        # the event id the game's bnk_sfx_1061303 carries for this name (read from the real bank)
        self.assertEqual(SN.fnv1("sfx_1061303_left_release2_play"), 2585212496)
        self.assertEqual(SN.fnv1("SFX_1061303_LEFT_RELEASE2_PLAY"), 2585212496)

    def test_rebuild_identity_and_replace(self):
        g = bank()
        self.assertIn(SN.alignment(g), (16, 32, 64))  # the largest power of two the vanilla offsets allow
        self.assertEqual(SN.rebuild(g, {}), g, "an unedited rebuild is byte-identical")
        new = SN.encode_wem(b"\1\0" * 960, 48000, 1)
        b = SN.rebuild(g, {1002: new})
        self.assertEqual(SN.readback(g, b, {1002: new}), [])
        self.assertEqual(SN.media_bytes(b)[1002], new)
        self.assertEqual(SN.media_bytes(b)[1001], SN.media_bytes(g)[1001])
        self.assertEqual([m for m, _, _ in SN.media(b)], [1001, 1002, 1003], "DIDX order kept")
        self.assertTrue(all(off % 16 == 0 for _, off, _ in SN.media(b)))
        self.assertIn("media 1002 is not the replacement", SN.readback(g, SN.rebuild(g, {}), {1002: new})[0])
        with self.assertRaises(ForgeError):
            SN.rebuild(g, {4242: new})
        tampered = b.replace(b"HIRC", b"HIRC", 1)[:-1] + b"\x01"
        self.assertTrue(any("HIRC" in p for p in SN.readback(g, tampered, {1002: new})))

    def test_event_map(self):
        ev = SN.event_map(bank(), [EVENT, f"sfx_{SKIN}_q_release_play"])
        e = ev[EVENT]
        self.assertEqual((e["primary"], e["variations"], e["layers"]), ([1001, 1002], True, [1003]))
        self.assertEqual(ev[f"sfx_{SKIN}_q_release_play"]["primary"], [1003])
        unnamed = SN.event_map(bank(), [])
        self.assertIn(str(SN.fnv1(EVENT)), unnamed)

    def test_pcm_wem(self):
        w = SN.encode_wem(struct.pack("<3h", 1, -2, 3), 44100, 1)
        self.assertEqual(w[:4], b"RIFF")
        self.assertEqual(struct.unpack_from("<I", w, 4)[0], 80 + 12)
        self.assertEqual(SN.wem_info(w), {"codec": "pcm", "channels": 2, "rate": 44100})
        self.assertEqual(struct.unpack_from("<I", w, 28)[0], 44100 * 4)
        self.assertEqual(w[96:100], b"data")
        self.assertEqual(w[104:], struct.pack("<6h", 1, 1, -2, -2, 3, 3), "mono written to both channels")
        self.assertEqual(len(SN.silence()), 104 + SN.SILENCE_FRAMES * 4)
        with self.assertRaises(UsageError):
            SN.encode_wem(b"", 48000, 2)

    def test_media_path(self):
        self.assertEqual(SN.media_path("bnk_display_1061303.bnk", 569659816), "Media/56/569659816.wem")
        self.assertEqual(SN.media_path("English(US)/bnk_vo_1061001.bnk", 1061177482),
                         "Media/English(US)/10/1061177482.wem")
        self.assertEqual(SN.full_path("../../../Marvel/", "Content/WwiseAudio/a.bnk"), "Marvel/Content/WwiseAudio/a.bnk")
        self.assertEqual(SN.full_path("../../../Marvel/Content/WwiseAudio/", "/a.bnk"), "Marvel/Content/WwiseAudio/a.bnk")


class SoundPipeline(ForgeCase):
    def setUp(self):
        super().setUp()
        self.stream_id = 569659816
        b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
        old = bank()[:-1] + b"\x07"  # the base pak's older bank; the patch pak's newer one must win
        new = bank()
        audio = {
            "pakchunkWwise-Windows.pak": {"mount": "../../../Marvel/Content/WwiseAudio/", "files": {
                f"/bnk_sfx_{SKIN}.bnk": b64(old), f"/bnk_display_{SKIN}.bnk": b64(bank(self.stream_id, display=True)),
                f"Media/56/{self.stream_id}.wem": b64(vorbis(5))}},
            # the patch pak holds a newer sfx bank: it must win over the base pak's
            "Patch_-Windows_1.1.4066382_P.pak": {"mount": "../../../Marvel/", "files": {
                f"Content/WwiseAudio/bnk_sfx_{SKIN}.bnk": b64(new)}},
        }
        (self.paks / "fake_audio.json").write_text(json.dumps(audio), encoding="utf-8")
        for name in audio:
            (self.paks / name).write_bytes(b"")
        fv = json.loads((self.paks / "fake_vanilla.json").read_text(encoding="utf-8"))
        for ev in (EVENT, f"sfx_{SKIN}_q_release_play", f"display_{SKIN}_mvp_play"):
            fv["packages"][f"Marvel/Content/Marvel/Wwise/Assets/WwiseEvents/Characters/1061/{SKIN}/ability/{ev}.uasset"] = {"kind": "event"}
        (self.paks / "fake_vanilla.json").write_text(json.dumps(fv), encoding="utf-8")
        self.ready()
        from mrforge.home import home
        from mrforge.util import save_json
        save_json(home() / "keys.json", {"mainKey": "0x" + "ab" * 32, "source": "test"})
        code, d = self.cli("new", "Loud Claws", "--skin", SKIN, "--kind", "sound", "--out", str(self.tmp / "snd"))
        self.assertEqual(code, 0, d)
        self.root = Path(d["data"]["project"])
        self.assertIn("extract --sounds", d["data"]["next"])

    def test_loop(self):
        code, d = self.cli("extract", "--sounds", cwd=self.root)
        self.assertEqual(code, 0, d)
        got = {x["bank"]: x for x in d["data"]["sounds"]}
        self.assertEqual(got[f"bnk_sfx_{SKIN}.bnk"]["from"], "Patch_-Windows_1.1.4066382_P.pak", "patch pak wins")
        code, d = self.cli("sound", "list", "*left*", cwd=self.root)
        self.assertEqual(code, 0, d)
        row = d["data"]["events"][0]
        self.assertEqual((row["event"], row["variations"], row["layers"]), (EVENT, 2, [1003]))
        src = wav(self.tmp / "claw.wav")
        code, d = self.cli("sound", "replace", EVENT, str(src), cwd=self.root)
        self.assertEqual(code, 0, d)
        self.assertEqual((d["data"]["replaced"], d["data"]["silenced"]), ([1001, 1002], [1003]))
        self.assertIn(f"sfx_{SKIN}_q_release_play", d["data"]["shared_with"], "the silenced layer is shared: warned")
        code, d = self.cli("sound", "replace", f"display_{SKIN}_mvp_play", str(src), cwd=self.root)
        self.assertEqual(code, 0, d)
        code, d = self.cli("build", cwd=self.root)
        self.assertEqual(code, 0, d)
        self.assertEqual((d["data"]["container"], d["data"]["routes"]), ("pak", ["sound"]))
        dist = self.root / "dist"
        self.assertEqual(sorted(p.suffix for p in dist.glob("*_9999999_P.*")), [".pak"], "sound-only: one .pak")
        pak = json.loads(next(dist.glob("*.pak")).read_text(encoding="utf-8"))
        self.assertIn(f"Marvel/Content/WwiseAudio/Media/56/{self.stream_id}.wem", pak["files"], "streamed copy packed")
        built = base64.b64decode(pak["files"][f"Marvel/Content/WwiseAudio/bnk_sfx_{SKIN}.bnk"])
        self.assertEqual(SN.wem_info(SN.media_bytes(built)[1001])["codec"], "pcm")
        self.assertEqual(SN.media_bytes(built)[1003], SN.silence())
        code, d = self.cli("validate", cwd=self.root)
        self.assertEqual(code, 0, d)
        rules = {r["rule"]: r["status"] for r in d["data"]["rules"]}
        self.assertEqual(rules["V-SND"], "pass")
        self.assertEqual(rules["V-CONFLICT"], "pass")
        code, d = self.cli("package", cwd=self.root)
        self.assertEqual(code, 0, d)
        self.assertEqual([e.rsplit(".", 1)[1] for e in d["data"]["entries"]], ["pak"])
        code, d = self.cli("deploy", cwd=self.root)
        self.assertEqual(code, 0, d)
        self.assertEqual(len(d["data"]["files"]), 1)

    def test_tampered_pak_and_bank_conflict(self):
        self.cli("extract", "--sounds", cwd=self.root)
        self.cli("sound", "replace", EVENT, str(wav(self.tmp / "a.wav")), cwd=self.root)
        code, d = self.cli("build", cwd=self.root)
        self.assertEqual(code, 0, d)
        pak_file = next((self.root / "dist").glob("*.pak"))
        other = self.mods_dir / "Other Sound Mod"
        other.mkdir()
        (other / "Other_9999999_P.pak").write_text(pak_file.read_text(encoding="utf-8"), encoding="utf-8")
        pak = json.loads(pak_file.read_text(encoding="utf-8"))
        key = f"Marvel/Content/WwiseAudio/bnk_sfx_{SKIN}.bnk"
        b = bytearray(base64.b64decode(pak["files"][key]))
        b[-1] ^= 0xFF  # inside HIRC
        pak["files"][key] = base64.b64encode(bytes(b)).decode()
        pak_file.write_text(json.dumps(pak), encoding="utf-8")
        code, d = self.cli("validate", cwd=self.root)
        rules = {r["rule"]: r for r in d["data"]["rules"]}
        self.assertEqual(rules["V-SND"]["status"], "fail")
        self.assertEqual(rules["V-CONFLICT"]["status"], "warn")
        self.assertIn("Other Sound Mod", rules["V-CONFLICT"]["detail"])

    def test_mixed_with_texture_is_one_iostore_container(self):
        self.cli("extract", "--sounds", "--textures", f"T_{SKIN}_Body_01_D", cwd=self.root)
        self.cli("tex", "hue", f"T_{SKIN}_Body_01_D", "--shift", "40", cwd=self.root)
        self.cli("sound", "replace", "--media", "1002", str(wav(self.tmp / "b.wav", ch=2)), cwd=self.root)
        code, d = self.cli("build", cwd=self.root)
        self.assertEqual(code, 0, d)
        self.assertEqual((d["data"]["container"], d["data"]["packer"]), ("iostore", "uassettool"))
        self.assertEqual(sorted(d["data"]["routes"]), ["sound", "texture"])
        code, d = self.cli("validate", cwd=self.root)
        rules = {r["rule"]: r["status"] for r in d["data"]["rules"]}
        self.assertEqual((rules["V-SND"], rules["V-TEX"]), ("pass", "pass"), d)

    def test_replace_needs_extraction_and_a_target(self):
        code, d = self.cli("sound", "list", cwd=self.root)
        self.assertEqual(d["errors"][0]["code"], "SOUNDS_NOT_EXTRACTED")
        self.cli("extract", "--sounds", cwd=self.root)
        code, d = self.cli("sound", "replace", "nope_play", str(wav(self.tmp / "c.wav")), cwd=self.root)
        self.assertEqual(d["errors"][0]["code"], "SOUND_EVENT_UNKNOWN")
        code, d = self.cli("sound", "replace", str(wav(self.tmp / "c.wav")), cwd=self.root)
        self.assertEqual(code, 2, d)
        code, d = self.cli("sound", "replace", EVENT, str(self.tmp / "missing.ogg"), cwd=self.root)
        self.assertEqual(code, 2, d)
        code, d = self.cli("sound", "replace", EVENT, str(wav(self.tmp / "c.wav")), cwd=self.root)
        self.assertEqual(code, 0, d)
        code, d = self.cli("sound", "reset", EVENT, cwd=self.root)
        self.assertEqual(len(d["data"]["reset"]), 3)
        code, d = self.cli("build", cwd=self.root)
        self.assertEqual(d["errors"][0]["code"], "NOTHING_TO_BUILD")


if __name__ == "__main__":
    unittest.main()
