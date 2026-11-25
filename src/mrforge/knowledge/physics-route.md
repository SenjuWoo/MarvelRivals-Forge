# Physics route (v1.0): jiggle, hair and cloth via KawaiiPhysics chains

No Unreal Editor needed. Verified at the package tier on build 4066382 (skin 1061303). Physics only shows in
motion in game: deploy, move the hero in the practice range, then `mrforge check-load --confirm`.

```
mrforge new "Jiggle" --skin 1061303 --kind physics
cd projects/jiggle
mrforge extract --physics                  # Post_<skin>_Physics (+ _Lobby_Physics) -> JSON
mrforge phys list                          # nodes in evaluation order, chains, root bones, parameters
mrforge phys add-chain --root L_Breast_01_Jnt --root R_Breast_01_Jnt --preset jiggle
mrforge phys set Damping 0.25 --bone "*hair*"          # tune existing chains
mrforge build && mrforge validate && mrforge package
```

What the asset is
- Each skin has a post-process AnimBlueprint `Post_<skin>_Physics` (in-match) and usually
  `Post_<skin>_Lobby_Physics` (hero select). The game runs it after the animation; its KawaiiPhysics nodes
  simulate hair, cloth, tails and accessories.
- In the class default object every anim node is one struct property; a node's input pose is a pose link whose
  `LinkID` indexes the AnimNode properties. Following the links from `AnimNode_Root` gives the evaluation order.
- Each `AnimNode_KawaiiPhysics` holds `Chains[]`. A chain has a root bone (its children swing), optional extra
  roots, a dummy tip length and its own physics settings. The game's own data uses up to 11 chains per node.

How add-chain works
1. A copy of the host node's first chain is appended with the new root bone and the chosen parameters. The anim
   graph, class layout and every other node stay byte-for-byte vanilla (verified: the CDO re-parses after
   `from_json`; the unchanged round trip keeps `.uexp` identical).
2. Default host: the KawaiiPhysics node evaluated last, so the new chain runs after the constraint/rivet nodes
   (on 1061303 two RivetConstraint nodes read the breast bones before any KawaiiPhysics node runs).
3. Unversioned headers: when a zero field becomes non-zero (e.g. `DummyBoneLength`), only the holding struct's
   header is dropped so UAssetTool rebuilds it. Dropping the node-level header corrupts the export (verified).
4. `mrforge build` converts the JSON back with `from_json` and reads the built asset straight back; `validate`
   reads it again out of the packed mod (rule V-PHYS: every chain, root and parameter present).

Parameters (per chain): Damping, Stiffness, WorldDampingLocation, WorldDampingRotation, Radius, LimitAngle,
LimitLinear, GravityScale, bUseCurve, TeleportDistanceThreshold, TeleportRotationThreshold, DummyBoneLength.
Presets: `mrforge phys presets` (jiggle, bouncy, firm). Lower Damping/Stiffness = more motion; lower
WorldDamping* = more follow-through when the hero moves; LimitAngle caps the swing; DummyBoneLength (cm) adds a
virtual tip so the last real bone rotates too.

Finding bones
- `mrforge mesh export` + `mrforge mesh blend`, then look at the armature in Blender; common soft-tissue bones on
  female skins: `L_Breast_01_Jnt` -> `L_Breast_02_Jnt` (and `R_`), `L_ButtScale`/`R_ButtScale`, `thigh_muscle_*`.
- `add-chain` warns when the bone name is not in the asset's name map; a wrong name simulates nothing.

Lobby / hero select: springs (v1.1, Unreal 5.3.2 headless)
- Lobby assets can have no KawaiiPhysics node at all (1061303's lobby asset has 34 nodes, none KawaiiPhysics), so
  `add-chain` cannot extend them. `mrforge phys springs --bone <bone> ...` records spring-bone jiggle instead
  (presets reference = stiffness 80, damping 6, 3 cm, the values of a working community lobby mod; soft; firm).
- `--region chest|butt|thighs` (repeatable) expands to the female body rig's soft-tissue bones: chest =
  `L/R_Breast_01_Jnt`, `_02_Jnt`; butt = `L/R_ButtScale`; thighs = `thigh_muscle_01..03_l/_r`. The 1061303 rig has
  no belly bone (the spine bones carry the torso; springing them sways the whole upper body).
- The build refuses a spring bone the skeleton lacks (SPRING_BONE_UNKNOWN) or whose skin weights, with its
  children's, are all zero (SPRING_BONE_UNWEIGHTED): both would compile and move nothing.
- At `mrforge build`: the vanilla blueprint is exported as FModel JSON and its mesh's skeleton as FBX (game
  containers only); UE 5.3.2 imports the skeleton, creates the blueprint at the vanilla path, rebuilds every vanilla
  node with the KawaiiPhysicsRivals importer (the build fails if it skips a node type), and the forge's
  MrforgeAnimTools plugin links Input Pose to the open inputs, appends the springs (space conversions inserted by
  the anim schema) and connects the last one to Output Pose, then compiles. Only the cooked blueprint is packed.
- `build` and V-PHYS read the blueprint back out of the mod with the game's mappings: every spring present, with its
  stiffness/damping/displacement, and on the path to the output pose.
- Requires doctor route `physics-lobby`: Unreal 5.3.2, Visual Studio 2022 Build Tools with an MSVC v143 toolset
  UE 5.3 accepts (14.36 preferred; 14.34-14.38), kawaii-physics-rivals (`mrforge setup`).
- Behaviour change: the vanilla BlendListByInt is driven by a curve the importer does not rebuild, so the PoseDriver
  correctives stay on. One asset is edited either with chains (JSON) or rebuilt with springs, not both.

Limits
- A chain that runs after a rivet leaves rivet-driven accessories following the un-jiggled pose.
- Installed mods that replace the same `Post_*` asset win or lose by load order; V-CONFLICT names them.
