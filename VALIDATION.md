# VALIDATION

Evidence per tier. `static`, `build`, `package` are proven by the forge; `load` and `gameplay` only by an in-game
look (`mrforge check-load --confirm`). "live" = run on the build machine against the installed game and tools.

## v0.1.0 - 2026-11-15, game build 1.1.4042190 (Season 11.0)

| Check | Result | How |
|---|---|---|
| Offline suite | pass (all tests) | `python tests/run_tests.py` (synthetic game, tool shims) |
| `mrforge setup --from <tool collection>` | pass: 4 tools adopted, probes `retoc-rivals-cli 3.11.1`, `UAssetTool v1.5.9+404737c3...`, `FModel.Mcp`, Oodle present | live |
| Release asset + exe hashes | pass: all four exe hashes inside the downloaded release zips equal `tools.lock.json` | live download |
| `mrforge sync` | pass: exact mapping for 4042190, SHA-256 `726e3d5b...83ad` | live |
| `mrforge index` | pass: 314,521 packages, 39 containers, 4.9 s | live |
| `mrforge doctor` | exit 0; texture, material, mesh-export, mesh-build available; 16 installed mods flagged (encrypted pak index) | live |
| `mrforge skin inspect 1061303` | `SK_1061_1061303` 18 material slots, `_Lobby` 19; `T_1061303_Body_01_D` 2048x2048 PF_DXT1 12 mips; shared 1061001 assets listed; 7 packages overridden by an installed mod | live |
| `mrforge selftest texture` | static/build/package pass; 1 package; flags `Compressed, Indexed`; V-TEX round trip PF_DXT1, 12 mips, RMSE 0.328% vs edit; 16 s | live |
| Material route | 2 materials (game + Lobby) built; V-MAT reads `BaseTint` and a formerly zero `BackRimColor` back from the packed mod | live |
| Deploy / undeploy | pass: recursive listing of `~mods` (986 entries) identical before deploy and after undeploy, except the `~mods` folder's own mtime | live |
| `check-load` | pass: scans newest game log + Galacta.log, reports deploy state and loader | live |
| load / gameplay | **not_run**: no forge-built mod has been looked at in game yet (assumptions A1, A3, A5) | owner |
