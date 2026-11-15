# STATE

Version: 0.1.0 (texture + material routes)
Updated: 2026-11-15

## Goal

A GitHub repository an agent can be pointed at to make Marvel Rivals skin mods efficiently: CLI `mrforge`,
pinned tools, facts from the installed game, build -> validate -> package -> deploy with tiered evidence.

## Done

- Planning (PLAN.md "Verified ground truth").
- T01-T27: package, CLI, all v0.1 modules, knowledge, tests (offline, tool shims), docs, installer, CI workflow,
  release builder. Live runs on the build machine: setup, sync, index, doctor, skin inspect, texture selftest,
  material route, deploy/undeploy, check-load, install/uninstall. Evidence: PLAN.md task table, VALIDATION.md.
- UE 5.3.2 is installed now and detected (mesh-build route `available`).

## Not done / not verified

- load / gameplay tiers: no forge-built mod has been looked at in game yet (assumptions A1, A3, A5).
- T28 publish, T29 registration, T30-T34 (v0.2 mesh route, physics).

## NEXT ACTION

PLAN.md T28: commit, create the public repository, push, converge CI on the exact SHA, query alerts, tag v0.1.0,
release with the T27 assets, re-hash the published asset.

## Build / run

- Tests: `python tests/run_tests.py`
- From the checkout: `mrforge.cmd <command>`; installed: `mrforge <command>` (Install.ps1)
- Release archive: `python tools/build_release.py` -> `artifacts/`

## How to resume

1. Read `WORKSPACE_OWNERSHIP.md`, this file, `PLAN.md`, `LOCAL.md` (private).
2. Take the first task whose Status is not `done`; run its Verify; record Evidence; update NEXT ACTION here.

## Log

- 2026-11-15 planning session; same day build session T01-T27.
