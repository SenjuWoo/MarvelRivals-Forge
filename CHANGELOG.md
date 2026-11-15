# Changelog

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
