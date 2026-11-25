---
name: marvelrivals-forge
description: Make, check, package and deploy Marvel Rivals skin mods (recolors, retextures, logos, skin tone, material tints and glow, body-shape and outfit mesh edits, jiggle/hair/cloth physics) with the mrforge CLI. Use for any Marvel Rivals mod, .pak/.utoc/.ucas, ~mods, skin id, texture, material, mesh or physics edit request.
version: 1.1.0
---

# MarvelRivals-Forge (mrforge 1.1.0)

Every command prints JSON `{ok, data, errors[{code,message,fix}], warnings, gaps}`; exit 0/1/2 (usage)/3
(environment). Follow `errors[].fix`. If `mrforge` is not on PATH, run `mrforge.cmd` from the forge folder.

## Cold start (and after every game patch)
1. `mrforge doctor` - fix every `fail` (a patch shows as `usmap: fail` -> `mrforge sync`, then `mrforge index`).
2. `mrforge setup` (or `--from <folder with tool copies>`), `mrforge sync`, `mrforge index`.

## Make a mod
1. `mrforge plan "<request>"` - route + exact commands. Routes: `texture`, `material`, `physics` (no editor),
   `mesh` (Blender + UE 5.3.2). One project can combine them: `--kind texture,mesh,physics`.
2. `mrforge skin find "<name>"` then `mrforge skin inspect <skinId>` (materials, textures, physics assets,
   shared assets, mods already overriding it).
3. `mrforge new "<Mod Name>" --skin <skinId> --kind <kinds>` and `cd` into the printed project.
4. Extract what you edit: `mrforge extract --textures "T_<skinId>_Body_*"` / `--materials` / `--physics`;
   meshes: `mrforge mesh export --lobby` then `mrforge mesh blend`.
5. Edit:
   - textures: `mrforge tex hue|tint|levels|overlay|replace <texture> ... [--mask m.png]` (never colour-edit `_N`)
   - materials: `mrforge mat set <MI> <Param> <value>`
   - physics: `mrforge phys list`, `mrforge phys add-chain --root <bone> [--root <bone>] --preset jiggle|bouncy|firm`,
     `mrforge phys set <Param> <value> --bone "<glob>"`
   - meshes: edit `work/mesh/*.blend` in Blender, or `mrforge mesh inflate --bone <bone> --factor 1.2`
6. Look before building: `mrforge tex sheet` -> `build/preview/sheet.png`; `mrforge mesh preview` ->
   `build/preview/<mesh>.png`; `mrforge mesh check` must pass.
7. `mrforge build` (one container for every edit; cooks only edited meshes), `mrforge validate` (all
   static/build/package rules pass: V-TEX, V-MAT, V-PHYS, V-MESH as applicable), `mrforge package`.
8. Only if the user wants it in game: `mrforge deploy`; after they look: `mrforge check-load --confirm "<note>"`.

## Jiggle (chest/butt)
- In matches: `mrforge extract --physics`, then
  `mrforge phys add-chain --root L_Breast_01_Jnt --root R_Breast_01_Jnt --preset jiggle` (no editor).
- In the lobby / hero select (what people look at first): `mrforge phys springs --bone L_Breast_01_Jnt
  --bone L_Breast_02_Jnt --bone R_Breast_01_Jnt --bone R_Breast_02_Jnt --bone L_ButtScale --bone R_ButtScale`.
  The build rebuilds the vanilla lobby blueprint in Unreal 5.3.2 plus spring-bone nodes (needs the
  `physics-lobby` doctor route: VS 2022 MSVC v143). One asset takes either chains or springs, not both.
- Check bone names in Blender after `mesh blend`; the build refuses spring bones the skeleton lacks.

## Do not
- edit files under the game folder or `~mods` yourself; `deploy`/`undeploy` do it with receipts.
- use obfuscate/strip/encrypt options; report load/gameplay as passed without the user's confirmation.
- rename bones or material slots in Blender; skip `mrforge mesh check` before building meshes.
- assume your mod wins over an installed mod for the same skin: V-CONFLICT names them; disable them to test.
