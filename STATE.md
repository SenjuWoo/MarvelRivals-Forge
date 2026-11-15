# STATE

Version: 0.2.0 (texture, material and mesh routes)
Updated: 2026-11-15

## Goal

A GitHub repository an agent can be pointed at to make Marvel Rivals skin mods efficiently: CLI `mrforge`,
pinned tools, facts from the installed game, build -> validate -> package -> deploy with tiered evidence.

## Done

- v0.1.0 released (T01-T28): texture and material routes; CI green, 0 alerts, published asset re-hashed.
- v0.2.0 (T30-T33): mesh route through Blender and Unreal Engine 5.3.2 verified at the package tier for skin
  1061303 (in-match + lobby). Evidence: PLAN.md task table, VALIDATION.md.
- T29 private part: PROJECTS.md row, SAFE-TOOLS.md verdicts, launcher on PATH.

## Not done / not verified

- load / gameplay tiers: no forge-built mod has been looked at in game yet. First owner check: deploy the texture
  selftest mod or a mesh mod, open the hero in the lobby, `mrforge check-load --confirm "<what you saw>"`.
- T29 bundle part (companion registry + ai-tooling-stack row) lives in the bundle repository; proposed separately.
- T34 physics route (optional).

## NEXT ACTION

Owner in-game check (A1/A3, mesh load). Then T34 if wanted.

## Build / run

- Tests: `python tests/run_tests.py`
- From the checkout: `mrforge.cmd <command>`; installed: `mrforge <command>` (Install.ps1)
- Release archive: `python tools/build_release.py` -> `artifacts/`
- Live smoke: `mrforge selftest texture`, `mrforge selftest mesh --lobby`

## How to resume

1. Read `WORKSPACE_OWNERSHIP.md`, this file, `PLAN.md`, `LOCAL.md` (private).
2. Take the first task whose Status is not `done`; run its Verify; record Evidence; update NEXT ACTION here.

## Log

- 2026-11-15 planning session; build session T01-T28 (v0.1.0 released), T30-T33 (v0.2.0).
