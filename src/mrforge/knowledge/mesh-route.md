# Mesh route: body shape, outfit edits, new geometry

Verified end to end at the package tier on build 4042190 (skin 1061303, in-match + lobby meshes). In-game load is
still owner-observed: deploy, look in the lobby and in a match, then `mrforge check-load --confirm`.

```
mrforge doctor                         # mesh-export and mesh-build must be available
mrforge new "Body Edit" --skin 1061303 --kind mesh
cd projects/body-edit
mrforge mesh export --lobby            # vanilla .uemodel + materials + PNG (lobby mesh too)
mrforge mesh blend                     # work/mesh/SK_<hero>_<skin>.blend (+ _Lobby.blend)
# edit the .blend files in Blender: sculpt/move vertices, keep bones, weights and material slots
mrforge mesh inflate --bone L_Breast_01_Jnt --bone R_Breast_01_Jnt --factor 1.2   # optional scripted edit
mrforge mesh preview                   # build/preview/<mesh>.png: vanilla | edited, front and side: look at it
mrforge mesh check                     # bones, hierarchy, slot names/order, vertex groups vs vanilla
mrforge build                          # cooks edited meshes (Unreal 5.3.2) + any texture/material/physics edits
mrforge validate && mrforge package
```

How it works (each step verified)
1. Export: fmodel-mcp opens a temporary folder of hardlinks to the top-level game containers, so installed mods
   can never become the base (fmodel-mcp otherwise mounts `~mods` too and exports the modded mesh).
2. Blender: ueformat-blender imported headless with sockets and virtual bones off; the armature then equals the
   mesh's reference skeleton (481 bones for SK_1061_1061303; with sockets on it gained 7 bones and extra roots).
3. FBX for Unreal: the armature object is renamed `Armature` (otherwise Unreal adds a root bone) and every slot gets
   its own material named exactly like the game's slot. Blender names materials after the material asset, so two
   slots sharing one instance would merge into one FBX material and shift every later slot.
4. Unreal 5.3.2 (`.mrforge/ue/Marvel`, IoStore off): the FBX is imported at the vanilla package path. Placeholders
   are created at the vanilla paths the cooked mesh must reference: the hero's Skeleton and PhysicsAsset (usually
   under `<hero>001`), the post-process AnimBP (`Post_<skin>_Physics`) and one MaterialInstanceConstant per slot
   (including VFX material paths). The game's MaterialTag gameplay tags go into RivalsMeshMaterialManager user data.
5. Cook **versioned** (no `-unversioned`): an unversioned stock cook writes properties by stock UE's class schema,
   which differs from the game's; the game's mappings then misread the mesh.
6. Pack with UAssetTool `create_mod_iostore` (not retoc, which refuses tagged cooks): it converts to the game's
   unversioned layout, pads `FSkeletalMaterial` and injects the slot tags, and strips the user data.
7. Verify: the mesh is extracted back out of the built mod and read with the game's mappings; bone count, slot
   names/order and every slot's tags must equal vanilla. Then it is exported from vanilla + the mod (as the game
   loads it) and every bone's local position, rotation and scale must equal vanilla, and 95% of the normals must
   be within 5 degrees (rule V-MESH). Placeholders are never packed (V-LEAK).

Units (fixed in 1.0.1): the FBX is written natively in centimetres with no object scale. Exporting metres put
scale 100 on the cooked root bone and the game collapsed the mesh onto its bones; putting the conversion in the
FBX unit factor instead left the bones 100x too small. Normals are imported, not recomputed.

Rules
- Keep bone names, hierarchy and material slots (names and order). Add geometry to existing slots.
- Edit both meshes when the change should show in hero select too; otherwise the lobby shows vanilla (V-MESH warns).
- A skin's body mesh may already be replaced by an installed mod; V-CONFLICT names it. Disable it to see yours.

Body-shape op: `mesh inflate` moves each vertex away from (factor > 1) or toward (< 1) the bone's head by
`(factor - 1) x weight`, where weight is the vertex's weight on the bone and its children. Bones, weights, slots
and shape-key deltas stay as they are, so `mesh check` passes. Every edit is logged in `work/mesh/edits.json`;
`mesh blend --force` re-imports vanilla.

One container: `mrforge build` puts edited meshes and any texture, material and physics edits into one mod (packed
with UAssetTool when meshes are present). It cooks only meshes whose `.blend` differs from the import;
`mrforge mesh build` cooks every exported mesh (unchanged round trip, used by `selftest mesh`).

Physics (jiggle/cloth): see `mrforge knowledge physics-route`.
