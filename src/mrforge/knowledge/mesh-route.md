# Mesh route (v0.2): body shape, outfit edits, new geometry

Verified end to end at the package tier on build 4042190 (skin 1061303, in-match + lobby meshes). In-game load is
still owner-observed: deploy, look in the lobby and in a match, then `mrforge check-load --confirm`.

```
mrforge doctor                         # mesh-export and mesh-build must be available
mrforge new "Body Edit" --skin 1061303 --kind mesh
cd projects/body-edit
mrforge mesh export --lobby            # vanilla .uemodel + materials + PNG (lobby mesh too)
mrforge mesh blend                     # work/mesh/SK_<hero>_<skin>.blend (+ _Lobby.blend)
# edit the .blend files in Blender: sculpt/move vertices, keep bones, weights and material slots
mrforge mesh check                     # bones, hierarchy, slot names/order, vertex groups vs vanilla
mrforge mesh build                     # Unreal 5.3.2 import + cook, UAssetTool pack, verify vs vanilla
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
   names/order and every slot's tags must equal vanilla (rule V-MESH). Placeholders are never packed (V-LEAK).

Rules
- Keep bone names, hierarchy and material slots (names and order). Add geometry to existing slots.
- Edit both meshes when the change should show in hero select too; otherwise the lobby shows vanilla (V-MESH warns).
- A skin's body mesh may already be replaced by an installed mod; V-CONFLICT names it. Disable it to see yours.

Physics (jiggle/cloth) is not covered yet; `retoc-rivals-cli fix-kawaii-physics` is the planned base.
