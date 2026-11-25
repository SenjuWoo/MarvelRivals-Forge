# Changelog

## 1.0.0 - 2026-11-25

Physics route, scripted body-shape edits and one build for every route.

- Physics route (no Unreal Editor): `mrforge extract --physics` converts the skin's post-process AnimBlueprints
  (`Post_<skin>_Physics`, `_Lobby_Physics`) to JSON; `mrforge phys list` shows every KawaiiPhysics chain in
  evaluation order; `phys add-chain --root <bone> --preset jiggle|bouncy|firm` adds a chain (e.g. chest jiggle) to
  the KawaiiPhysics node that runs last; `phys set <Param> <value> --bone <glob>` tunes existing hair, cloth and
  tail chains; `phys presets`, `phys reset`. The anim graph stays untouched; `build` reads every physics edit back
  at once and `validate` rule V-PHYS reads it back out of the packed mod. `selftest physics`.
- `mrforge mesh inflate --bone <b> --factor <f>`: weight-driven body-shape edit (grow/shrink around bones) on the
  in-match and lobby `.blend` files; bones, weights, slots and shape-key deltas kept; logged in `work/mesh/edits.json`.
- `mrforge mesh preview`: vanilla | edited renders (front, side) in `build/preview/<mesh>.png`.
- `mrforge build` builds every route into one container: textures, materials, physics and edited meshes (only
  meshes whose `.blend` changed are cooked). With meshes the packer is UAssetTool, otherwise retoc.
  `mrforge mesh build` is the same build with every exported mesh cooked.
- `doctor` reports the physics route; `plan` routes jiggle/cloth/hair requests to it; `new --kind physics`.
- Verified against game build 1.1.4066382: live end-to-end test mod on skin 1061303 (body texture hue, chest
  inflate on both meshes, chest jiggle chains) passes every static/build/package rule.
- Fixes: `extract` no longer lists earlier extractions as unrequested; stale "v0.2 preview" messages removed.

## 0.2.0 - 2026-11-15

Mesh route: body shape and outfit geometry edits through Blender and Unreal Engine 5.3.2, verified against vanilla.

- `mrforge mesh build`: imports the edited mesh in a generated UE 5.3.2 project at the vanilla path, binds it to
  placeholder skeleton, physics asset, post-process AnimBP and material instances at the vanilla paths, writes the
  game's per-slot MaterialTag gameplay tags (RivalsMeshMaterialManager), cooks versioned, packs with UAssetTool
  and reads the mesh back with the game's mappings (bones, slot names/order and tags must equal vanilla).
- In-match and lobby meshes in one mod; `validate` rule V-MESH; `selftest mesh [--lobby]`.
- Blender import without sockets/virtual bones (the armature equals the reference skeleton); FBX export renames
  the armature to `Armature` and gives every slot a unique material named like the game's slot.
- Pinned RivalsMeshMaterialManager v1.2.0 in `tools.lock.json`; doctor's mesh-build route needs it.

- Mesh route preview: `mrforge mesh export [--lobby]` exports the skin's vanilla mesh through fmodel-mcp from a
  temporary hardlink view of the game containers (installed mods can never leak in), `mesh blend` imports it into
  Blender headless, `mesh fbx` writes FBX, `mesh check` compares bones, hierarchy, material slots and vertex groups
  with vanilla. `doctor` reports leftover views.
- Release and mod zips store entries uncompressed so they are byte-identical on every OS.

## 0.1.0 - 2026-11-15

First release: texture and material routes, editor-free.

- `mrforge` CLI with a JSON contract (`ok, command, version, data, errors, warnings, gaps`; exit 0/1/2/3).
- Setup of pinned tools (retoc-rivals-cli 3.11.1, UAssetTool 1.5.9, fmodel-mcp 1.2.0, UEFormat Blender v10) from
  GitHub releases or existing copies, verified by SHA-256.
- Game discovery through Steam, build/changelist, ASI loader and signature-bypass detection, installed-mod scan
  with encrypted/obfuscated/stripped flags and conflicts.
- Exact-build mapping download (`sync`), vanilla package index (`index`), hero/skin name table, `skin inspect`
  (meshes, material slots and tags, textures with format and mips, assets shared with other skins, overriding mods).
- Projects: `new`, `extract`, texture ops (`hue`, `tint`, `levels`, `overlay`, `replace`, masks, `sheet`),
  material parameters (`mat list/set/reset`), `build`, `validate` (9 rules, evidence tiers), deterministic
  `package`, receipt-based `deploy`/`undeploy`, `check-load` with log signatures and owner confirmation.
- `doctor`, `plan` (request router), `capabilities`, `guide`, `knowledge`, `facts`, `selftest texture`.
- Installer (`Install.ps1`, `Uninstall.ps1`, `START-HERE.bat`), agent skill, offline test suite with tool shims, CI.
