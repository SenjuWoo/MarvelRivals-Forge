---
name: marvelrivals-forge
description: Make, check, package and deploy Marvel Rivals skin mods (recolors, retextures, logos, skin tone, material tints and glow) with the mrforge CLI. Use for any Marvel Rivals mod, .pak/.utoc/.ucas, ~mods, skin id, or texture/material edit request.
version: 0.1.0
---

# MarvelRivals-Forge (mrforge 0.1.0)

Every command prints JSON `{ok, data, errors[{code,message,fix}], warnings, gaps}`; exit 0/1/2 (usage)/3
(environment). Follow `errors[].fix`. If `mrforge` is not on PATH, run `mrforge.cmd` from the forge folder.

## Cold start
1. `mrforge doctor` - fix every `fail`.
2. `mrforge setup` (or `--from <folder with tool copies>`), `mrforge sync`, `mrforge index`.

## Make a mod
1. `mrforge plan "<request>"` - gives the route and the exact commands. v0.1 routes: `texture`, `material`.
2. `mrforge skin find "<name>"` then `mrforge skin inspect <skinId>` (materials, textures, shared assets,
   mods already overriding it).
3. `mrforge new "<Mod Name>" --skin <skinId> --kind texture` and `cd` into the printed project.
4. `mrforge extract --textures "T_<skinId>_Body_*"` (or `--materials`, `--all`).
5. Edit: `mrforge tex hue|tint|levels|overlay|replace <texture> ... [--mask m.png]`,
   `mrforge mat set <MI> <Param> <value>`. Never colour-edit `_N` normal maps.
6. `mrforge tex sheet` and open `build/preview/sheet.png` - look at it before building.
7. `mrforge build`, `mrforge validate` (all static/build/package rules pass), `mrforge package`.
8. Only if the user wants it in game: `mrforge deploy`; after they look: `mrforge check-load --confirm "<note>"`.

## Do not
- edit files under the game folder or `~mods` yourself; `deploy`/`undeploy` do it with receipts.
- use obfuscate/strip/encrypt options; report load/gameplay as passed without the user's confirmation.
- claim mesh/body-shape or physics mods work in v0.1 (`mrforge plan` says what is available).
