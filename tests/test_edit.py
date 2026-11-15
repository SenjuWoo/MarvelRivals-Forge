"""Texture ops (determinism, masks, normal-map refusal, sheet) and material JSON edits."""
import copy
import hashlib

from helpers import ForgeCase, material_json

from mrforge.util import ForgeError


def _img(path, color=(200, 100, 50, 255), size=(16, 16)):
    from PIL import Image
    im = Image.new("RGBA", size, color)
    im.putpixel((0, 0), (10, 20, 30, 128))
    im.save(path)
    return path


def _h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TexOps(ForgeCase):
    with_game = False

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "proj"
        (self.root / "work" / "textures").mkdir(parents=True)
        (self.root / "vanilla" / "png").mkdir(parents=True)
        self.lock = {"textures": {}}
        for n in ("T_1_Body_01_D", "T_1_Body_01_N", "T_1_Body_01_ORM"):
            v = _img(self.root / "vanilla" / "png" / f"{n}.png")
            w = self.root / "work" / "textures" / f"{n}.png"
            w.write_bytes(v.read_bytes())
            self.lock["textures"][n] = {"package": f"x/{n}.uasset", "vanilla_png": f"vanilla/png/{n}.png",
                                        "work_png": f"work/textures/{n}.png", "png_sha256": _h(v), "width": 16, "height": 16}

    def test_hue_deterministic_and_idempotent(self):
        from mrforge import tex as X
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "hue", "shift": 90.0})
        w = self.root / "work" / "textures" / "T_1_Body_01_D.png"
        h1 = _h(w)
        X.regenerate_all(self.root, self.lock)
        X.regenerate_all(self.root, self.lock)
        self.assertEqual(_h(w), h1)
        self.assertEqual(X.changed(self.root, self.lock), ["T_1_Body_01_D"])
        from PIL import Image
        self.assertEqual(Image.open(w).getpixel((0, 0))[3], 128)  # alpha kept

    def test_normal_map_refused(self):
        from mrforge import tex as X
        with self.assertRaises(ForgeError) as cm:
            X.add_op(self.root, self.lock, "T_1_Body_01_N", {"op": "tint", "color": [255, 0, 0], "strength": 1.0})
        self.assertEqual(cm.exception.code, "COLOUR_OP_ON_NORMAL_MAP")
        X.add_op(self.root, self.lock, "T_1_Body_01_N", {"op": "hue", "shift": 10.0}, force=True)

    def test_packed_warns(self):
        from mrforge import tex as X
        r = X.add_op(self.root, self.lock, "T_1_Body_01_ORM", {"op": "levels", "black": 10, "white": 240, "gamma": 1.2})
        self.assertTrue(r["warnings"])

    def test_mask_limits_edit(self):
        from PIL import Image
        from mrforge import tex as X
        mask = self.tmp / "mask.png"
        m = Image.new("L", (16, 16), 0)
        for x in range(8):
            for y in range(16):
                m.putpixel((x, y), 255)
        m.save(mask)
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "tint", "color": [0, 0, 255], "strength": 1.0}, mask=str(mask))
        im = Image.open(self.root / "work" / "textures" / "T_1_Body_01_D.png").convert("RGBA")
        self.assertNotEqual(im.getpixel((4, 4))[:3], (200, 100, 50))
        self.assertEqual(im.getpixel((12, 4))[:3], (200, 100, 50))

    def test_overlay_and_replace_resize(self):
        from PIL import Image
        from mrforge import tex as X
        logo = _img(self.tmp / "logo.png", (0, 255, 0, 255), (4, 4))
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "overlay", "opacity": 1.0, "at": [2, 2]}, src=str(logo))
        im = Image.open(self.root / "work" / "textures" / "T_1_Body_01_D.png")
        self.assertEqual(im.getpixel((3, 3))[:3], (0, 255, 0))
        big = _img(self.tmp / "big.png", (9, 9, 9, 255), (64, 64))
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "replace", "keep_size": False}, src=str(big))
        self.assertEqual(Image.open(self.root / "work" / "textures" / "T_1_Body_01_D.png").size, (16, 16))
        ops = X.load_ops(self.root)["textures"]["T_1_Body_01_D"]["ops"]
        self.assertEqual([o["op"] for o in ops], ["replace"])  # replace drops earlier ops

    def test_hand_edit_conflict(self):
        from mrforge import tex as X
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "hue", "shift": 30.0})
        _img(self.root / "work" / "textures" / "T_1_Body_01_D.png", (1, 2, 3, 255))
        with self.assertRaises(ForgeError) as cm:
            X.regenerate_all(self.root, self.lock)
        self.assertEqual(cm.exception.code, "HAND_EDIT_CONFLICT")
        painted = self.tmp / "painted.png"
        painted.write_bytes((self.root / "work" / "textures" / "T_1_Body_01_D.png").read_bytes())
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "replace", "keep_size": False}, src=str(painted))
        X.regenerate_all(self.root, self.lock)

    def test_sheet_dimensions(self):
        from PIL import Image
        from mrforge import tex as X
        X.add_op(self.root, self.lock, "T_1_Body_01_D", {"op": "hue", "shift": 90.0})
        r = X.sheet(self.root, self.lock, thumb=64)
        self.assertEqual(Image.open(r["sheet"]).size, (2 * 64 + 3 * 8, 64 + 18 + 8 + 8))
        X.reset(self.root, self.lock, "T_1_*_D")
        with self.assertRaises(ForgeError):
            X.sheet(self.root, self.lock)

    def test_parse_color(self):
        from mrforge.tex import parse_color
        self.assertEqual(parse_color("#ff8000"), (255, 128, 0))
        self.assertEqual(parse_color("1,0.5,0"), (255, 128, 0))


class MatJson(ForgeCase):
    with_game = False

    def test_params_and_parent(self):
        from mrforge import mat as M
        d = material_json()
        ps = {p["name"]: p for p in M.params(d)}
        self.assertEqual(ps["AOIntensity"]["value"], 0.0)  # "+0" string float
        self.assertEqual(ps["BaseTint"]["value"], [1.0, 1.0, 1.0, 0.0])
        self.assertEqual(ps["BackRimColor"]["value"], [0.0, 0.0, 0.0, 0.0])  # IsZero, no value
        self.assertTrue(ps["BaseColor"]["value"].endswith("T_1061303_Body_01_D"))
        self.assertTrue(M.parent(d).endswith("M_1061001_Skin.M_1061001_Skin"))
        self.assertEqual(len(M.package_refs(d)), 2)

    def test_set_vector_scalar_and_zero(self):
        from mrforge import mat as M
        d = copy.deepcopy(material_json())
        M.set_param(d, "BaseTint", M.parse_value("vector", "#ff0000"))
        M.set_param(d, "Roughness", M.parse_value("scalar", "0.25"))
        M.set_param(d, "BackRimColor", [0.2, 0.4, 0.6, 1.0])
        ps = {p["name"]: p["value"] for p in M.params(d)}
        self.assertEqual(ps["BaseTint"], [1.0, 0.0, 0.0, 1.0])
        self.assertEqual(ps["Roughness"], 0.25)
        self.assertEqual(ps["BackRimColor"], [0.2, 0.4, 0.6, 1.0])
        ent = [e for p in d["Exports"][0]["Data"] if p["Name"] == "VectorParameterValues" for e in p["Value"]][1]
        self.assertIsNone(ent["OriginalStructHeader"])  # stale zero mask dropped (verified necessary on the real tool)
        with self.assertRaises(ForgeError):
            M.set_param(d, "NoSuchParam", 1.0)
        with self.assertRaises(ForgeError):
            M.parse_value("texture", "x")
        with self.assertRaises(ForgeError):
            M.parse_value("vector", "1,2")
