# STATE

Version: 1.2.2 (knowledge records Texture/ and Material/ folders; 1.2.1: extract fix, launcher exit code, README and cover)
Updated: 2026-11-25
Last known-good release: v1.2.2 (see the v1.2.2 tag; CI green on the tagged commit); previous v1.2.1

## Goal

A GitHub repository an agent can be pointed at to make Marvel Rivals skin mods efficiently: CLI `mrforge`,
pinned tools, facts from the installed game, build -> validate -> package -> deploy with tiered evidence.

## Done

- v0.1.0 (T01-T28): texture and material routes. v0.2.0 (T30-T33): mesh route through Blender + UE 5.3.2.
- v1.0.0 (T35-T41, released): game build 4066382 refresh; physics route (`extract --physics`, `phys list/add-chain/set/
  reset/presets`, V-PHYS); `mesh inflate`, `mesh preview`; unified `build` (one container, edited meshes only);
  live test mod `projects/forge-v1-test` (skin 1061303: body texture hue 150, chest inflate x1.25 on both meshes,
  chest jiggle chains) passes every static/build/package rule and is deployed to `~mods/ZZZ-mrforge-forge-v1-test`.
  Evidence: PLAN.md v1.0.0 table, VALIDATION.md.

- v1.0.1 (T43): first in-game look of v1.0.0's test mod: texture showed (load tier for textures confirmed), mesh
  collapsed onto its bones. Root cause: cooked root bone scale 100 from FBX units; plus recomputed normals. Fixed
  (centimetre FBX, imported normals) and V-MESH now checks bind pose + normals read back from the built mod. Fixed
  test mod redeployed.

- In game (owner, 2026-11-25): v1.0.1 mesh + texture correct in the lobby (load tier confirmed for texture and
  mesh). No jiggle in the lobby, as expected: the chains were in-match only.
- v1.1.0 (T44): `phys springs` lobby route: vanilla lobby graph rebuilt in UE 5.3.2 (KawaiiPhysicsRivals importer),
  MrforgeAnimTools C++ plugin (VS 2022 MSVC 14.36) wires it and appends spring bones, cooked at the vanilla path.
  Test mod rebuilt with 6 lobby springs (breasts 01/02, butt) + in-match chains; validate all pass; redeployed.
  VS 2022 Build Tools installed (owner-approved); `setup --from` folder-adoption bug fixed.
- Owner 2026-11-25: lobby chest jiggle visible in game (check-load recorded, gameplay tier). Then `--region
  chest|butt|thighs` and the SPRING_BONE_UNWEIGHTED guard; test mod rebuilt with 12 lobby springs (chest, butt,
  thighs; the rig has no belly bone) and in-match chains on chest + butt; validate all pass; redeployed. Released
  as v1.1.0.
- v1.2.0 (T46-T47): sound route (`extract --sounds`, `sound list/replace/reset`, in-place PCM media in the skin's
  Wwise banks, HIRC untouched, V-SND, bank V-CONFLICT, pak-only sound mods). Test mod gets a three-tone beep on
  primary fire (left_release1..3) and the hero-select hover sound. Owner heard the beep in game (check-load
  recorded, gameplay tier). Released as v1.2.0.
- Animation research (2026-11-25): per-skin animation assets exist for hero select, hero details, MVP and camera
  (1061303: Animations/HeroDetails, Mvp, Camera); combat animations are the hero's (1061001) and shared by every
  skin, except a few rig-changing skins (e.g. 1016502, 1018300) that ship whole sets. Not a route yet.
- v1.2.1 (presentation pass, released): `extract` now selects `Texture/` and `Material/` folders (240 of 751 skin
  folders in build 4066382 use `Texture/`, 24 use `Material/`; live: Storm 1015001 extract + tint + build +
  validate + package pass, 1031502 `extract --materials` selects 33); `mrforge.cmd` passes exit codes through
  with a `.venv`; README rewritten with `docs/presentation/` cover and terminal shots from real runs; icon
  `docs/icon.svg`. Tests 103.
- v1.2.2: asset-layout doc and fact `layout.singular_folders`; `skin list` hint names Storm; README catalog/CI
  wording.

## Not done / not verified

- In game: butt/thigh springs and the in-match chains not yet looked at.
- Animation route (per-skin lobby/MVP animations through UE 5.3.2 import + cook) not built.
- T29 bundle part (companion registry + ai-tooling-stack row) lives in the bundle repository.

## NEXT ACTION

None required. Optional: owner look at butt/thigh jiggle and in-match chains; an animation route if wanted.

## Build / run

- Tests: `python tests/run_tests.py`
- From the checkout: `mrforge.cmd <command>`; installed: `mrforge <command>` (Install.ps1)
- Release archive: `python tools/build_release.py` -> `artifacts/`
- Live smoke: `mrforge selftest texture`, `mrforge selftest physics`, `mrforge selftest mesh --lobby`
- Remove the test mod from the game: `mrforge undeploy forge-v1-test`
- Log: `.mrforge/logs/` (one JSON line per CLI call)

## How to resume

1. Read `WORKSPACE_OWNERSHIP.md`, this file, `PLAN.md`, `LOCAL.md` (private).
2. Take the first task whose Status is not `complete`; run its Verify; record Evidence; update NEXT ACTION here.

## Log

- 2026-11-15 planning session; build session T01-T28 (v0.1.0 released), T30-T33 (v0.2.0).
- 2026-11-25 v1.0.0 session: game patched to 4066382; physics route, inflate/preview, unified build, live test mod.
- 2026-11-25 owner in-game look: mesh deformed -> v1.0.1 (root-bone scale + normals fixed, V-MESH bind pose).
- 2026-11-25 owner: mesh/texture OK in game, no lobby jiggle -> v1.1.0 lobby springs (UE headless, own plugin).
- 2026-11-25 owner: lobby chest jiggle works -> regions (butt, thighs), weight guard, v1.1.0 released.
- 2026-11-25 owner: sounds the RoR2 way (no Wwise download) -> v1.2.0 sound route (in-place PCM bank media).
- 2026-11-25 owner heard the test beep -> v1.2.0 released; animation-per-skin researched (lobby/MVP only).
- 2026-11-25 presentation pass: two defects found by running the README for real -> v1.2.1.
