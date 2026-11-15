# MarvelRivals-Forge

A command-line forge for making **Marvel Rivals skin mods**, built so an AI agent (or a person) can go from
"make this skin red" to a validated, packaged mod in a handful of commands, without opening Unreal Editor.

- **One CLI, JSON everywhere**: `mrforge <command>` prints one JSON object with `ok`, `data`, `errors` (each with a
  fix), `warnings` and `gaps`.
- **Pinned tools**: retoc-rivals-cli, UAssetTool, fmodel-mcp and the UEFormat Blender importer are fetched by
  `mrforge setup` from their GitHub releases and checked against SHA-256 hashes in `tools.lock.json`.
- **Facts from your install**: game build, loader, installed mods and every vanilla package path are read from the
  game itself; the mapping file must match your exact game build.
- **Edit as recorded ops**: hue, tint, levels, overlay, replace (with masks) and material parameters are replayed
  from vanilla on every build, so edits never stack or drift.
- **Evidence tiers**: `validate` proves static, build and package tiers (including extracting the edited texture back
  out of the built mod); load and gameplay are recorded only from an in-game look.

## Requirements

Windows, Python 3.10+, a Steam install of Marvel Rivals, and the ASI loader + UTOC signature bypass for loading
mods (`mrforge doctor` checks it). Unreal Engine 5.3.2 and Blender 4.2+ are needed only for the mesh route.

## Quick start

```powershell
git clone https://github.com/SenjuWoo/MarvelRivals-Forge
cd MarvelRivals-Forge
.\Install.ps1            # venv + 'mrforge' on your PATH (or run .\mrforge.cmd without installing)
mrforge doctor
mrforge setup
mrforge sync
mrforge index
mrforge selftest texture # end-to-end smoke run, never deploys
```

## Make a mod

```powershell
mrforge plan "make Black Cat's suit red"
mrforge skin find "black cat"
mrforge new "Red Cat" --skin <skinId> --kind texture
cd projects\red-cat
mrforge extract --textures "T_<skinId>_Body_*"
mrforge tex tint T_<skinId>_Body_01_D --color "#c01020" --strength 0.7
mrforge tex sheet        # look at build\preview\sheet.png
mrforge build
mrforge validate
mrforge package          # dist\RedCat-0.1.0.zip for your mod manager
mrforge deploy           # optional: copies into ~mods\ZZZ-mrforge-red-cat\
```

`mrforge capabilities` lists every command; `mrforge guide` prints the runbook; `mrforge knowledge` lists the docs.

## Routes

| Route | What | Status |
|---|---|---|
| texture | recolor, retexture, logos, decals, skin tone | v0.1 |
| material | material instance tints, glow, roughness | v0.1 |
| mesh | body shape, outfit geometry edits (Blender + UE 5.3.2), in-match and lobby meshes | v0.2 |
| physics | jiggle / cloth tuning | later |

## Safety

The forge never writes into the game folder except `mrforge deploy` into its own `ZZZ-mrforge-<id>` folder (with a
receipt that `undeploy` uses to remove exactly what it added), never edits mod-manager state, and only builds plain
containers: since Season 11 the game reports encrypted, obfuscated and stripped mods. See `SECURITY.md`.

## License

MIT for this repository. The upstream tools keep their own licenses; see `THIRD-PARTY.md`.
