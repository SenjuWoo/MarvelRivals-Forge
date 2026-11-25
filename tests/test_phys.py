"""Physics route: anim-graph order, chain listing, add-chain/set edits, header rule, verify, CLI loop with shims."""
import copy
import json
from pathlib import Path

from helpers import SKIN, ForgeCase, physics_json

from mrforge import phys as PH
from mrforge.util import ForgeError, UsageError


class PhysJson(ForgeCase):
    with_game = False

    def setUp(self):
        super().setUp()
        self.d = physics_json()

    def test_eval_order_and_default_host(self):
        names = [p["Name"] for p in PH.anim_nodes(self.d)]
        order = [names[i] for i in PH.eval_order(self.d)]
        self.assertEqual(order, ["AnimGraphNode_LinkedInputPose", "RivetConstraint", "AnimGraphNode_KawaiiPhysics",
                                 "AnimGraphNode_KawaiiPhysics_1", "AnimGraphNode_Root"])
        # The node evaluated last hosts new chains: it runs after the rivet that writes the same bones.
        self.assertEqual(PH.default_host(self.d), "AnimGraphNode_KawaiiPhysics_1")

    def test_listing(self):
        info = PH.listing(self.d)
        self.assertEqual((info["anim_nodes"], info["kawaii_nodes"], len(info["chains"])), (5, 2, 3))
        first = info["chains"][0]
        self.assertEqual(first["node"], "AnimGraphNode_KawaiiPhysics")  # evaluated first
        self.assertEqual(first["roots"], ["hair_A1", "hair_A1_B"])
        self.assertEqual(first["params"]["Damping"], 0.35)
        self.assertEqual(first["params"]["DummyBoneLength"], 0.0)

    def test_add_chain(self):
        node = PH.find_node(self.d, "AnimGraphNode_KawaiiPhysics_1")
        node_header = copy.deepcopy(node["OriginalStructHeader"])
        r = PH.add_chain(self.d, "R_Breast_01_Jnt", PH.parse_params(None, "jiggle"))
        self.assertEqual((r["host"], r["chain"]), ("AnimGraphNode_KawaiiPhysics_1", 1))
        el = PH.child(node, "Chains")["Value"][1]
        self.assertEqual(el["Name"], "1")
        self.assertEqual(PH.roots_of(el), ["R_Breast_01_Jnt"])  # template's extra roots dropped
        self.assertEqual(PH.get_param(el, "DummyBoneLength"), 6.0)
        self.assertIs(PH.get_param(el, "bUseCurve"), False)
        # zero -> non-zero: the holding struct's header goes; the node header never (D25)
        self.assertIsNone(PH.child(el, "BoneSettings")["OriginalStructHeader"])
        self.assertEqual(node["OriginalStructHeader"], node_header)
        self.assertIsNotNone(PH.child(PH.child(el, "PhysicsSettings"), "PhysicsSettings")["OriginalStructHeader"])
        self.assertIn("R_Breast_01_Jnt", self.d["NameMap"])
        tmpl = PH.child(node, "Chains")["Value"][0]
        self.assertEqual(PH.roots_of(tmpl), ["Collar_A1", "Collar_A1_B"])  # template untouched

    def test_add_chain_refuses_simulated_bone_and_missing_host(self):
        with self.assertRaises(ForgeError) as e:
            PH.add_chain(self.d, "hair_B1", {})
        self.assertEqual(e.exception.code, "PHYS_BONE_ALREADY_SIMULATED")
        with self.assertRaises(ForgeError) as e:
            PH.add_chain(physics_json(with_kawaii=False), "L_Breast_01_Jnt", {})
        self.assertEqual(e.exception.code, "PHYS_NO_KAWAII_NODE")
        with self.assertRaises(ForgeError) as e:
            PH.add_chain(self.d, "L_Breast_01_Jnt", {}, host="Nope")
        self.assertEqual(e.exception.code, "PHYS_NODE_NOT_FOUND")

    def test_set_and_verify(self):
        ops = [{"op": "add_chain", "root": "L_Breast_01_Jnt", "params": {"Damping": 0.1, "DummyBoneLength": 5.0}},
               {"op": "set", "bone": "hair_*", "param": "Stiffness", "value": 0.2}]
        self.assertTrue(PH.verify(self.d, ops))  # vanilla lacks the edits
        done = PH.apply_ops(self.d, ops)
        self.assertEqual(done[1]["chains"], ["AnimGraphNode_KawaiiPhysics[0]", "AnimGraphNode_KawaiiPhysics[1]"])
        self.assertEqual(PH.verify(self.d, ops), [])
        with self.assertRaises(ForgeError):
            PH.apply_ops(self.d, [{"op": "set", "bone": "nothing*", "param": "Damping", "value": 1}])

    def test_unparsed_export_named(self):
        self.d["Exports"][1]["Data"] = "AAEC=="
        with self.assertRaises(ForgeError) as e:
            PH.listing(self.d)
        self.assertEqual(e.exception.code, "PHYS_UNPARSED")

    def test_parse_params(self):
        p = PH.parse_params(["Damping=0.4", "bUseCurve=yes"], "firm")
        self.assertEqual(p["Damping"], 0.4)
        self.assertIs(p["bUseCurve"], True)
        self.assertEqual(p["LimitAngle"], PH.PRESETS["firm"]["LimitAngle"])
        for bad in (["Wobble=1"], ["Damping"]):
            with self.assertRaises(UsageError):
                PH.parse_params(bad, None)
        with self.assertRaises(UsageError):
            PH.parse_params(None, "squishy")


class PhysPipeline(ForgeCase):
    def setUp(self):
        super().setUp()
        self.ready()
        code, d = self.cli("new", "Jiggle Test", "--skin", SKIN, "--kind", "physics", "--out", str(self.tmp / "p"))
        self.assertEqual(code, 0, d)
        self.assertIn("extract --physics", d["data"]["next"])
        self.root = Path(d["data"]["project"])

    def run_cli(self, *a):
        return self.cli(*a, cwd=self.root)

    def test_loop(self):
        code, d = self.run_cli("extract", "--physics")
        self.assertEqual(code, 0, d)
        self.assertEqual(d["data"]["physics"], 2)
        self.assertTrue(any("no KawaiiPhysics node" in w for w in d["warnings"]))  # the lobby asset
        code, d = self.run_cli("phys", "list")
        assets = {a["asset"]: a for a in d["data"]["assets"]}
        self.assertEqual(assets[f"Post_{SKIN}_Physics"]["kawaii_nodes"], 2)
        self.assertEqual(assets[f"Post_{SKIN}_Lobby_Physics"]["kawaii_nodes"], 0)
        code, d = self.run_cli("phys", "add-chain", "--root", "L_Breast_01_Jnt", "--root", "R_Breast_01_Jnt",
                               "--param", "Damping=0.12")
        self.assertEqual(code, 0, d)
        self.assertEqual([x["asset"] for x in d["data"]["added"]], [f"Post_{SKIN}_Physics"] * 2)  # lobby skipped
        self.assertTrue(any("R_Breast_01_Jnt" in w for w in d["warnings"]))  # not in the vanilla name map
        code, d = self.run_cli("phys", "set", "Stiffness", "0.3", "--bone", "hair_*")
        self.assertEqual(code, 0, d)
        code, d = self.run_cli("phys", "add-chain", "--root", "L_Breast_01_Jnt")
        self.assertEqual(d["errors"][0]["code"], "PHYS_BONE_ALREADY_SIMULATED")
        ops = json.loads((self.root / "work" / "phys_ops.json").read_text(encoding="utf-8"))
        self.assertEqual(len(ops["assets"][f"Post_{SKIN}_Physics"]), 3)  # the refused op is not stored
        code, d = self.run_cli("build")
        self.assertEqual(code, 0, d)
        self.assertEqual((d["data"]["routes"], d["data"]["packer"], d["data"]["packages"]),
                         (["physics"], "retoc-rivals-cli", 1))
        code, d = self.run_cli("validate")
        self.assertEqual(code, 0, d)
        st = {r["rule"]: r["status"] for r in d["data"]["rules"]}
        self.assertEqual((st["V-PHYS"], st["V-LEAK"], st["V-PATHS"]), ("pass", "pass", "pass"))
        code, d = self.run_cli("phys", "reset")
        self.assertEqual(code, 0, d)
        code, d = self.run_cli("build")
        self.assertEqual(d["errors"][0]["code"], "NOTHING_TO_BUILD")

    def test_v_phys_fails_when_edit_missing_from_mod(self):
        self.run_cli("extract", "--physics")
        self.run_cli("phys", "add-chain", "--root", "L_Breast_01_Jnt")
        code, d = self.run_cli("build")
        self.assertEqual(code, 0, d)
        ops_file = self.root / "work" / "phys_ops.json"
        ops = json.loads(ops_file.read_text(encoding="utf-8"))
        ops["assets"][f"Post_{SKIN}_Physics"][0]["params"]["Damping"] = 0.99  # what the mod should have
        ops_file.write_text(json.dumps(ops), encoding="utf-8")
        code, d = self.run_cli("validate")
        st = {r["rule"]: r for r in d["data"]["rules"]}
        self.assertEqual(st["V-PHYS"]["status"], "fail")
        self.assertIn("Damping", st["V-PHYS"]["detail"])


class MeshChanges(ForgeCase):
    with_game = False

    def test_only_edited_blends_build(self):
        from mrforge.build import mesh_packages
        from mrforge.util import save_json, sha256_file
        root = self.tmp / "proj"
        mesh = root / "work" / "mesh"
        mesh.mkdir(parents=True)
        pk = [f"Marvel/Content/x/SK_A{s}.uasset" for s in ("", "_Lobby")]
        save_json(mesh / "export.json", {"meshes": [{"package": p} for p in pk]})
        for p in pk:
            b = mesh / (Path(p).stem + ".blend")
            b.write_bytes(b"vanilla")
            save_json(mesh / (Path(p).stem + ".vanilla.json"), {"blend_sha256": sha256_file(b)})
        self.assertEqual(mesh_packages(root), [])
        self.assertEqual(mesh_packages(root, force=True), pk)
        (mesh / "SK_A_Lobby.blend").write_bytes(b"edited")
        self.assertEqual(mesh_packages(root), [pk[1]])

    def test_inflate_arguments_checked(self):
        from mrforge.mesh import inflate
        with self.assertRaises(UsageError):
            inflate(self.tmp, [], 1.2)
        with self.assertRaises(UsageError):
            inflate(self.tmp, ["spine_04"], 5.0)



def spring_json(bones=("L_Breast_01_Jnt",), stiffness=80.0, wired=True):
    """Post-process CDO: input(1) -> L2C(2) -> springs -> C2L -> Root(0), shaped like a cooked spring blueprint."""
    from helpers import _node, _struct, _f
    nodes = [None, _node("AnimGraphNode_LinkedInputPose", "AnimNode_LinkedInputPose", "InputPose", -1),
             _node("AnimGraphNode_LocalToComponentSpace", "AnimNode_ConvertLocalToComponentSpace", "LocalPose", 1)]
    prev = 2
    for i, b in enumerate(bones):
        nodes.append(_node(f"AnimGraphNode_SpringBone_{i}", "AnimNode_SpringBone", "ComponentPose", prev,
                           [_struct("SpringBone", "BoneReference", [{"Name": "BoneName", "Value": b}]),
                            _f("SpringStiffness", stiffness), _f("SpringDamping", 6.0), _f("MaxDisplacement", 3.0)]))
        prev = len(nodes) - 1
    nodes.append(_node("AnimGraphNode_ComponentToLocalSpace", "AnimNode_ConvertComponentToLocalSpace", "ComponentPose", prev))
    nodes[0] = _node("AnimGraphNode_Root", "AnimNode_Root", "Result", len(nodes) - 1 if wired else 1)
    return {"NameMap": list(bones), "Exports": [{"ObjectName": "Post_X_C", "Data": []},
                                                {"ObjectName": "Default__Post_X_C", "Data": nodes}]}


class Springs(ForgeCase):
    with_game = False

    def _op(self, bones=("L_Breast_01_Jnt",), **kw):
        return {"op": "springs", "bones": list(bones), "params": PH.spring_params("reference", **kw)}

    def test_verify_springs(self):
        op = self._op(("L_Breast_01_Jnt", "R_Breast_01_Jnt"))
        self.assertEqual(PH.verify_springs(spring_json(("L_Breast_01_Jnt", "R_Breast_01_Jnt")), [op]), [])
        self.assertIn("R_Breast_01_Jnt missing", PH.verify_springs(spring_json(), [op])[0])
        self.assertIn("SpringStiffness", PH.verify_springs(spring_json(stiffness=50.0), [self._op()])[0])
        self.assertIn("does not feed", PH.verify_springs(spring_json(wired=False), [self._op()])[0])
        self.assertEqual(PH.verify(spring_json(), [op]), [])  # chain verifier ignores editor ops

    def test_spring_params(self):
        p = PH.spring_params("soft", damping=7)
        self.assertEqual((p["stiffness"], p["damping"], p["max_displacement"]), (50.0, 7.0, 4.0))
        self.assertEqual(p["rotate"], [False] * 3)
        with self.assertRaises(UsageError):
            PH.spring_params("wobbly")
        with self.assertRaises(UsageError):
            PH.spring_params(None, stiffness=0)

    def test_compiler_pick_prefers_ue53_tested_toolsets(self):
        from mrforge.uepost import pick_compiler
        self.assertEqual(pick_compiler(["14.44.35207", "14.38.33130", "14.36.32532"]), "14.36.32532")
        self.assertEqual(pick_compiler(["14.44.35207", "14.38.33130"]), "14.38.33130")
        self.assertIsNone(pick_compiler(["14.44.35207", "14.52.37025"]))

    def test_regions(self):
        self.assertEqual(PH.region_bones(["butt"], ["L_ButtScale"]), ["L_ButtScale", "R_ButtScale"])
        thighs = PH.region_bones(["thighs"], [])
        self.assertIn("thigh_muscle_01_l", thighs)
        self.assertEqual(len(PH.region_bones(["chest", "butt", "thighs"], [])), 12)
        with self.assertRaises(UsageError):
            PH.region_bones(["belly"], [])
        with self.assertRaises(UsageError):
            PH.region_bones([], [])

    def test_unweighted_springs(self):
        from mrforge.uepost import unweighted
        arm = [{"name": "pelvis", "parent": None}, {"name": "thigh_l", "parent": "pelvis"},
               {"name": "calf_l", "parent": "thigh_l"}, {"name": "ik_spine", "parent": "pelvis"},
               {"name": "L_ButtScale", "parent": "thigh_l"}]
        weighted = {"pelvis", "calf_l", "L_ButtScale"}
        # thigh_l carries no weight itself but its children do: it moves skin, so it is allowed
        self.assertEqual(unweighted(["L_ButtScale", "thigh_l", "ik_spine"], arm, weighted), ["ik_spine"])

    def test_mesh_for(self):
        from mrforge.uepost import mesh_for
        m = {"hero_id": "1061", "skin_id": SKIN}
        self.assertTrue(mesh_for(f"Post_{SKIN}_Lobby_Physics", m).endswith(f"SK_1061_{SKIN}_Lobby.uasset"))
        self.assertTrue(mesh_for(f"Post_{SKIN}_Physics", m).endswith(f"SK_1061_{SKIN}.uasset"))


class SpringsCli(ForgeCase):
    def setUp(self):
        super().setUp()
        self.ready()
        code, d = self.cli("new", "Lobby Bounce", "--skin", SKIN, "--kind", "physics", "--out", str(self.tmp / "s"))
        self.root = Path(d["data"]["project"])
        self.cli("extract", "--physics", cwd=self.root)

    def test_springs_default_to_lobby_and_refuse_mixing(self):
        code, d = self.cli("phys", "springs", "--bone", "L_Breast_01_Jnt", "--bone", "R_Breast_01_Jnt", cwd=self.root)
        self.assertEqual(code, 0, d)
        self.assertEqual([x["asset"] for x in d["data"]["added"]], [f"Post_{SKIN}_Lobby_Physics"])
        code, d = self.cli("phys", "springs", "--bone", "L_Breast_01_Jnt", cwd=self.root)
        self.assertEqual(d["errors"][0]["code"], "PHYS_BONE_ALREADY_SIMULATED")
        code, d = self.cli("phys", "add-chain", "--root", "X_Jnt", "--asset", f"Post_{SKIN}_Lobby_Physics", cwd=self.root)
        self.assertEqual(d["errors"][0]["code"], "PHYS_ROUTE_MIX")
        code, d = self.cli("phys", "add-chain", "--root", "L_Breast_01_Jnt", cwd=self.root)  # in-match asset: fine
        self.assertEqual(code, 0, d)
        code, d = self.cli("phys", "springs", "--bone", "Y", "--asset", f"Post_{SKIN}_Physics", cwd=self.root)
        self.assertEqual(d["errors"][0]["code"], "PHYS_ROUTE_MIX")

    def test_springs_by_region(self):
        code, d = self.cli("phys", "springs", "--region", "butt", "--region", "thighs", cwd=self.root)
        self.assertEqual(code, 0, d)
        bones = d["data"]["added"][0]["result"][0]["springs"]
        self.assertEqual(len(bones), 8)
        self.assertIn("R_ButtScale", bones)
        code, d = self.cli("phys", "springs", cwd=self.root)
        self.assertEqual(code, 2, d)
