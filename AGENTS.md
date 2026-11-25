# AGENTS.md - MarvelRivals-Forge runbook

You are pointed at this repository to make Marvel Rivals skin mods. Use the `mrforge` CLI; every command prints
one JSON object `{ok, command, version, data, errors[], warnings[], gaps[]}` and exits 0 ok, 1 failure, 2 usage,
3 environment. Read `errors[].fix` before trying anything else.

## Cold start (once per machine, again after a game patch)

```
mrforge doctor                 # what is missing, each check with a fix
mrforge setup                  # pinned tools into .mrforge/tools (add --from <folder> to adopt existing copies)
mrforge sync                   # mapping (.usmap) for the installed build + AES key
mrforge index                  # vanilla package index for this build (~5 s)
```

Not installed? `mrforge.cmd <command>` runs from the checkout, or run `Install.ps1` once for a PATH launcher.

## The loop

```
mrforge plan "<what the user asked for>"      # route + exact commands
mrforge skin find "<name>"  |  mrforge skin inspect <skinId>
mrforge new "<Mod Name>" --skin <skinId> --kind texture[,material,physics,mesh]
cd <project>
mrforge extract --textures "<glob>" | --materials | --physics | --all
mrforge mesh export --lobby && mrforge mesh blend          # mesh kind
mrforge tex ... / mrforge mat set ... / mrforge phys add-chain|set ... / mrforge mesh inflate ... (or Blender)
mrforge tex sheet / mrforge mesh preview   # LOOK at build/preview/*.png before building
mrforge mesh check                         # mesh kind
mrforge build                              # one container for every edit
mrforge validate             # static/build/package tiers; fix every fail
mrforge package              # zip for a mod manager
mrforge deploy               # only when the user wants it in game
mrforge check-load           # after the user looked in game; --confirm "<what they saw>"
```

## Sources of truth

| Question | Where |
|---|---|
| What exists in this game build | `mrforge index`, `mrforge skin inspect` (wins over the name table) |
| Skin names | `src/mrforge/knowledge/skins.json` (snapshot; newer skins show id only) |
| Verified facts with tier and source | `mrforge facts [--grep x]` |
| How a route works | `mrforge knowledge <topic>` |
| Tool versions and hashes | `tools.lock.json` |
| A project's state | `<project>/mrforge.json`, `vanilla.lock.json`, `work/ops.json`, `work/mat_ops.json`, `work/phys_ops.json`, `work/mesh/edits.json`, `dist/receipt.json` |

## Module map (`src/mrforge/`)

cli (parser, JSON contract) - home (forge home, config, log) - game (Steam discovery, build, loader) - tools
(lock, setup, run) - sync (usmap, key) - index (vanilla listing) - catalog (names) - skin (inspect) - mods
(installed mods, conflicts) - project (new, bump) - extract - tex (Pillow ops) - mat (material JSON) - phys (KawaiiPhysics chains in Post_*_Physics JSON) - build (every route,
one container) -
validate - package - deploy - checkload - selftest - doctor - knowledge (facts, routes, plan) - ue (UE 5.3.2
detection) - uat (UAssetTool output parsers) - mesh (export, Blender, inflate, preview, check) - uebuild (UE import +
cook) - fmcp (fmodel-mcp client) - blender/mesh_tool.py, unreal/import_mesh.py (headless scripts).

## Boundaries

- Read-only: the game folder, everything in `~mods` except `*-mrforge-*` folders, mod-manager staging, tool copies
  adopted with `--from`. The only game write is `mrforge deploy` into its own folder, with a receipt.
- Vanilla always comes from the game containers (never from installed mods).
- Never obfuscate, strip or encrypt a mod (the game reports those since Season 11).
- Load and gameplay are proven only by someone looking in game; report them as `not_run` until confirmed.
- Never commit game files or anything extracted from them. Tests use synthetic fixtures and tool shims.

## Developing the forge

- `python tests/run_tests.py` (offline, shims for both tools) stays green; every fix starts with a failing test.
- Read real tool output before coding against it; record what you verified in `knowledge/facts.json` with a tier.
- Version lives in `src/mrforge/__init__.py`; mirrors: `CHANGELOG.md` top entry, `STATE.md`, the skill file.
- Releases: `python tools/build_release.py`, CI green on the exact SHA, then tag and release.
