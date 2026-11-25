# VALIDATION

Evidence per tier. `static`, `build`, `package` are proven by the forge; `load` and `gameplay` only by an in-game
look (`mrforge check-load --confirm`). "live" = run on the build machine against the installed game and tools.

## v1.2.0 - 2026-11-25 (sound route)

| Check | Result | How |
|---|---|---|
| Game audio layout | banks + streamed media in `pakchunkWwise-Windows.pak` (mount `Marvel/Content/WwiseAudio/`), newer banks in the Patch pak; per-skin `bnk_sfx_1061303` (155 media, Vorbis) and `bnk_display_1061303` (4 streamed) | UAssetTool list_pak/extract_pak |
| Event names | FNV-1 of WwiseEvents package names matches the bank's event ids; 29 of 72 sfx events named, all 228 Sound objects reached from events | live |
| Bank rebuild | unedited rebuild byte-identical on bnk_sfx_1061303, bnk_display_1061303, bnk_ui_battle; one swap reads back clean | live |
| Offline suite | pass (101 tests) incl. bank format, event map, PCM .wem, extract/replace/build/validate/deploy loop, tampered pak, bank conflict, mixed container | `python tests/run_tests.py` |
| Live test mod | 3-tone beep on left_release1..3 (9 variations, 6 layers silenced) and display hover (streamed); build 287 s; validate all pass incl. V-SND; redeployed | live |
| load / gameplay (sound heard) | **pass**: the three-tone beep plays in game | owner, `check-load --tier gameplay` |

## v1.1.0 - 2026-11-25 (lobby springs)

| Check | Result | How |
|---|---|---|
| In-game look at v1.0.1 test mod | lobby: texture and fixed mesh **correct**; no jiggle (chains are in-match only) | owner screenshots |
| Reference mod analysis | community lobby jiggle = new AnimBlueprint with 12 SpringBone nodes on the lobby skeleton, mesh post-process relinked | retoc manifest + to_json |
| VS 2022 Build Tools | installed (Microsoft-signed bootstrapper, hash = URL hash); MSVC 14.36/14.38/14.44, SDK 22621/26100; a first copy installed at a wrong path was uninstalled | vswhere |
| MrforgeAnimTools build | UBT `-CompilerVersion=14.36.32532`: 20 actions, 0 errors, 45 s | live |
| Lobby blueprint in UE | 32 vanilla nodes, 30 links, 0 skipped types, 4 stubs (not packed), 6 springs, compiled 0 errors | live |
| Read-back from the mod | CDO NormalExport, 45 anim nodes; Root <- C2L <- 6 springs <- L2C <- vanilla chain; springs' stiffness/damping/displacement equal | live (V-PHYS) |
| Offline suite | pass (89 tests) incl. springs verify/params/compiler pick/route-mix, setup adoption bug | `python tests/run_tests.py` |
| `mrforge build` (test mod) | 5 packages (texture, in-match physics, lobby physics, 2 meshes), UAssetTool packer, bind pose equal, 520 s | live |
| `mrforge validate` (test mod) | static/build/package pass (V-TEX, V-PHYS x2, V-MESH, V-CONFLICT) | live |
| Redeploy | `~mods/ZZZ-mrforge-forge-v1-test` (zip SHA-256 `3e0178d1...420b`) | live |
| load / gameplay (lobby chest springs) | **pass**: chest jiggle visible in the lobby | owner, `check-load --tier gameplay` |
| `--region` + weight guard | rig weights read in Blender: ButtScale ~3.6k, thigh_muscle_01..03 0.9-2.6k weighted vertices; thigh_l/r none; no belly bone | live |
| Rebuild with 12 springs (chest, butt, thighs) + in-match chains on chest and butt | build ok (271 s, meshes reused), read-back 12 springs wired; validate all pass; redeployed | live |
| Offline suite | pass (92 tests) incl. regions, unweighted guard | `python tests/run_tests.py` |
| load / gameplay (butt/thigh springs, in-match chains) | **not_run**: owner look optional | owner |

## v1.0.1 - 2026-11-25 (mesh fix after the first in-game look)

| Check | Result | How |
|---|---|---|
| In-game look at the v1.0.0 test mod | texture **shown** (teal body, lobby); mesh **broken** (collapsed onto bones) | owner screenshot |
| Root cause | read back from the mod: `root` bone scale 100 (vanilla 1); every other bone, weight, order and shape key equal | UEFormat raw bone read |
| Fix attempt 1 (FBX_SCALE_ALL) | rejected: root scale 1 but all bone translations 100x too small (V-MESH bind pose fail) | live rebuild |
| Fix attempt 2 (centimetre data, scene unit 0.01) | bind pose of both meshes equal to vanilla (all bones: position, rotation, scale) | live rebuild + read-back |
| Normals | recomputed on import: p95 13.5 deg off vanilla; with imported normals p95 0.6 deg | live read-back |
| Offline suite | pass (83 tests) incl. bind-pose and normals rules | `python tests/run_tests.py` |
| `mrforge selftest mesh --lobby` | exit 0, both meshes bind pose equal to vanilla, 317 s (read-back adds about 2 min) | live |
| `mrforge validate` (fixed test mod) | static/build/package pass, V-MESH incl. bind pose + normals, V-PHYS, V-TEX; V-CONFLICT pass (BodyReshape mods disabled) | live |
| Redeploy | fixed mod in `~mods/ZZZ-mrforge-forge-v1-test` (zip SHA-256 `73480858...a716`) | live |
| load / gameplay (mesh, jiggle) | **not_run**: owner look pending | owner |

## v1.0.0 - 2026-11-25, game build 1.1.4066382 (Season 11.0), Unreal Engine 5.3.2, Blender 5.3.0

| Check | Result | How |
|---|---|---|
| Offline suite | pass (79 tests) incl. physics JSON edits, header rule, V-PHYS pass/fail, unified build, plan combine | `python tests/run_tests.py` |
| `mrforge sync` / `index` for the patched game | exact mapping for 4066382 (SHA-256 `a92c8164...3aad`); 318,153 packages, 40 containers, 5.9 s | live |
| Physics JSON round trip | `Post_1061303_Physics` to_json -> from_json: `.uexp` byte-identical; after appending chains the CDO re-parses and every value reads back | live spike |
| Header rule (D25) | dropping the node-level header -> RawExport (unparseable); dropping only BoneSettings' header -> values read back | live bisect |
| Mixed packing (D26) | UAssetTool `create_mod_iostore` with an injected texture + edited physics asset: both extract back (texture PF_DXT1 2048x2048 12 mips; chains intact) | live |
| `mrforge selftest physics` | exit 0: 2 chest chains added + 1 chain tuned, retoc packer, build read-back ok, V-PHYS pass, 16 s | live |
| `mrforge selftest texture` | exit 0, static/build/package pass, 13 s | live |
| `mrforge selftest mesh --lobby` | exit 0 through the unified build (both meshes cooked, V-MESH pass), 164 s | live |
| Test mod `forge-v1-test` (skin 1061303) | `mesh inflate` x1.25 on L/R_Breast_01_Jnt (2,358 / 2,443 vertices moved, max 2.2 cm), `mesh check` pass, `mesh preview` looked at; body texture hue 150 (sheet looked at); 2 chest jiggle chains (preset jiggle) on AnimGraphNode_KawaiiPhysics_5 | live |
| `mrforge build` (test mod) | 4 packages (texture, physics, 2 meshes) in one container, UAssetTool packer, mesh checks 481 bones/18 slots and 646/19 equal vanilla, physics read-back ok, 137 s | live |
| `mrforge validate` (test mod) | static/build/package pass: V-NAME, V-FLAGS (Compressed, Indexed), V-PATHS, V-LEAK, V-STALE, V-RECEIPT, V-TEX, V-PHYS, V-MESH; V-CONFLICT warns (installed BodyReshape mods replace the same mesh/texture) | live |
| `mrforge package` / `deploy` (test mod) | zip 6.2 MB (SHA-256 `e689fa46...2ba8`); deployed to `~mods/ZZZ-mrforge-forge-v1-test` with receipt | live |
| load / gameplay | **not_run**: waiting for the owner's in-game look (practice range for jiggle; disable the conflicting BodyReshape mods) | owner |

## v0.2.0 - 2026-11-15, game build 1.1.4042190 (Season 11.0), Unreal Engine 5.3.2, Blender 5.3.0

| Check | Result | How |
|---|---|---|
| Offline suite | pass (all tests) | `python tests/run_tests.py` incl. fake MCP server and reference parsing |
| `mrforge mesh export --lobby` | pass: both meshes from `pakchunkCharacter` while an installed mod overrides them; no view folder left; 29-46 s | live |
| `mrforge mesh blend` / `mesh check` | pass: 95,767 vertices, 481 bones, 18 slots; check fails after renaming a slot | live |
| `mrforge mesh build` | pass: in-match 481 bones / 18 slots, lobby 646 bones / 19 slots; read back from the mod with the game's mappings; slot names, order and all gameplay tags equal vanilla; container holds the 2 meshes only; 116 s | live |
| `mrforge validate` (mesh project) | static/build/package pass incl. V-MESH; V-CONFLICT warns about the installed body-reshape mod | live |
| `mrforge selftest mesh --lobby` | exit 0, 208 s | live |
| Unversioned cook (rejected route) | fail by design: unreadable with the game's mappings; retoc refuses the versioned cook | live spike |
| load / gameplay | **not_run**: no forge-built mod has been looked at in game yet | owner |

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
