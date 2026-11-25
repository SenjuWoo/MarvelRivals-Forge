# Changelog

## 1.2.1 - 2026-11-25

Fixes found while checking the README against real runs.

- Fixed: `mrforge extract --textures` matched nothing for skins whose textures live in a `Texture/` folder (about
  a third of all skins, Storm's default 1015001 among them); `--materials` had the same gap for `Material/`.
  Both folder spellings are now selected, and `skin inspect`'s deep material view lists textures from either.
- Fixed: the checkout launcher `mrforge.cmd` exited 0 on every failure when a `.venv` was present
  (`%ERRORLEVEL%` was read inside a parenthesised block). It now passes the forge's exit code through.
- README rewritten: cover image, real terminal shots, a tour that works with names in the skin table, the full
  command table and the install options. Icon in `docs/icon.svg`.

## 1.2.0 - 2026-11-25

Sound route: replace a skin's sounds with your own audio. No Wwise and no Unreal Editor.

- `mrforge extract --sounds` pulls the skin's Wwise banks (`bnk_sfx_<skin>`, `bnk_display_<skin>`; `--bank <name>`
  for others) from the game's sound paks, newest patch first, and maps every event name to its media.
- `mrforge sound list` shows events with their variations and layers; `mrforge sound replace <event> <file>` takes
  any audio ffmpeg reads (a 16-bit WAV needs no ffmpeg), cuts it at 30 s, applies `--gain`, puts it in every
  variation and silences stacked layers (`--keep-layers` keeps them); `--media <id>` replaces one media;
  `mrforge sound reset`.
- `build` writes the audio as Wwise PCM media in place in the bank (HIRC byte-identical, DIDX order and alignment
  kept; an unedited rebuild is byte-identical to the game's bank) plus the loose copy of a streamed sound. The
  banks go into the mod's companion pak; a sound-only mod is a single `.pak`.
- `build` and the new V-SND rule read the banks back out of the built pak. V-CONFLICT names installed mods that
  carry the same bank (the game loads one copy of a bank). Doctor route `sound`.
- `deploy` and `package` handle a pak-only mod and clear a stale file when a mod's container shape changes.

## 1.1.0 - 2026-11-25

Lobby (hero select) jiggle, built headless in Unreal Engine 5.3.2.

- `mrforge phys springs --bone <bone> ... [--preset reference|soft|firm]`: spring-bone jiggle in a post-process
  AnimBlueprint, by default `Post_<skin>_Lobby_Physics`, which has no KawaiiPhysics node for the chain route.
  At build time the vanilla graph is rebuilt from its FModel JSON (KawaiiPhysicsRivals importer), the forge's own
  editor plugin MrforgeAnimTools wires the graph ends and appends the springs before the output, and the blueprint
  is compiled, cooked and packed at its vanilla path (no mesh relink; the skeleton and importer stubs stay out of
  the mod). `build` reads it back from the mod (springs present, wired to the output); V-PHYS checks it again.
- `--region chest|butt|thighs` expands to the body rig's soft-tissue bones (breast joints, ButtScale, thigh
  muscle joints). The build refuses spring bones the skeleton lacks or that move no skin (zero weights on the bone
  and its children).
- MrforgeAnimTools (C++ editor plugin, source in `src/mrforge/unreal/MrforgeAnimTools`) is built once per source
  change with UBT pinned to a Visual Studio 2022 MSVC toolset UE 5.3 accepts (14.36 preferred, 14.34-14.38).
- Pinned KawaiiPhysicsRivals v2.1.0 in `tools.lock.json`; doctor route `physics-lobby`.
- Fixed: `mrforge setup --from` adopted the whole parent folder for tools whose executable sits under a package
  folder (it copied a 1.6 GB tool collection); it now adopts that folder only.
- Behaviour note: a rebuilt lobby graph keeps every vanilla node, but the vanilla BlendListByInt's curve binding is
  not rebuilt, so its PoseDriver correctives stay on.

## 1.0.1 - 2026-11-25

Mesh route fix: cooked meshes deformed in game (found by the first in-game look).

- Fixed: every cooked mesh had scale 100 on its root bone. Blender exported metres and Unreal kept the FBX unit
  factor as a root-bone scale, so the game shrank every vertex onto its bone (stick-figure model in the lobby).
  The FBX is now written natively in centimetres with no object scale (`to_centimetres` in the Blender helper).
- Fixed: Unreal recomputed normals on import (faceted seams at waist, hands and head); the import now keeps the
  FBX normals, which equal vanilla.
- V-MESH now reads each mesh back out of the built mod as the game loads it and compares every bone's position,
  rotation and scale with vanilla (bind pose) and the normals (95th percentile within 5 degrees). Both bugs above
  passed the old rule, which compared only bone count, slot names and tags.
- Texture and physics routes are unchanged; the texture edit of the test mod showed correctly in game.

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
