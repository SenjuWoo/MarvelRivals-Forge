# STATE

Version: 1.0.1 (texture, material, physics and mesh routes; one build for every route; mesh bind-pose fix)
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

- v1.0.1 (T43): first in-game look of v1.0.0's test mod: texture showed (load tier for textures confirmed), mesh
  collapsed onto its bones. Root cause: cooked root bone scale 100 from FBX units; plus recomputed normals. Fixed
  (centimetre FBX, imported normals) and V-MESH now checks bind pose + normals read back from the built mod. Fixed
  test mod redeployed.

## Not done / not verified

- load / gameplay tiers for the fixed mesh and the jiggle chains: waiting for the owner's look at the redeployed
  test mod (lobby for the mesh; practice range for jiggle, the lobby asset has no KawaiiPhysics node).
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
- 2026-11-25 owner in-game look: mesh deformed -> v1.0.1 (root-bone scale + normals fixed, V-MESH bind pose).
