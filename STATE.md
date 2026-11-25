# STATE

Version: 1.0.0 (texture, material, physics and mesh routes; one build for every route)
Updated: 2026-11-25
Last known-good release: v1.0.0 (tag on 132516c, CI green, published asset re-hashed)

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

## Not done / not verified

- load / gameplay tiers: no forge-built mod has been looked at in game yet (A1, A3, A11). The test mod is deployed;
  the installed BodyReshape mods for 1061303 (Vortex `AAE-`/`AAF-` folders) replace the same mesh and texture, so
  disable them in Vortex for a clean look. Jiggle shows in matches/practice range only (lobby asset has no
  KawaiiPhysics node).
- Lobby jiggle: needs an Unreal-authored AnimBlueprint (KawaiiPhysicsRivals importer is BlueprintCallable); not
  automated.
- T29 bundle part (companion registry + ai-tooling-stack row) lives in the bundle repository.

## NEXT ACTION

Owner in-game check of the deployed test mod (T42):
`mrforge check-load forge-v1-test --confirm "<what you saw>"`.

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
