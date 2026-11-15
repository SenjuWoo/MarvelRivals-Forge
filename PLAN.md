# PLAN - MarvelRivals-Forge

Goal: a GitHub repository an agent can be pointed at to make Marvel Rivals skin mods with the fewest steps:
one CLI (`mrforge`), pinned tools fetched by one command, facts read from the installed game, and a
build -> validate -> package -> deploy loop that reports evidence per tier.

Planned 2026-11-15 against game build `1.1.4042190` (Season 11.0). The builder starts here; machine paths
are in `LOCAL.md` (private, git-ignored). Read `WORKSPACE_OWNERSHIP.md`, `STATE.md`, this file, then `LOCAL.md`.

Rules for the builder
- One task at a time, in order. A task is done only when its Verify passes; write the result in Evidence and
  set Status to `done` (or `blocked: <exact reason>`). Update `STATE.md` NEXT ACTION after each task.
- Every fix starts with a failing test. `python tests/run_tests.py` stays green and offline.
- Game folder, `~mods`, mod-manager staging and the third-party tool collection are read-only. The only game
  write is `mrforge deploy` into its own `*-mrforge-*` folder.
- Never commit game files or anything extracted from them. Test fixtures are synthetic.
- Read tool behaviour from the tool (`--help`, real output) before coding against it. "Verified ground truth"
  below was observed on this machine; anything under "Assumptions" was not.
- No AI attribution in commits, docs or releases. Public files carry no machine paths or personal names.
- "live" in a Verify column means: run on this PC against the installed game and tools.

## Tasks

| ID | Task | Status | Depends on | Verify | Evidence |
|---|---|---|---|---|---|
| T01 | Repo init: `git init -b main`; `.gitignore` (`LOCAL.md`, `.venv/`, `.mrforge/`, `projects/`, `artifacts/`, `build/`, `dist/`, `__pycache__/`, `*.egg-info/`, `*.log`, `.pytest_cache/`); `.gitattributes` (LF default; CRLF for `*.bat *.cmd *.ps1`; `*.png` binary); `LICENSE` (MIT) | done | - | `git status --short --ignored` lists `LOCAL.md` as ignored; `git check-attr eol -- x.cmd` = crlf | `LOCAL.md` listed `!!` (ignored); `x.cmd: eol: crlf` |
| T02 | Package skeleton: `pyproject.toml` (setuptools, name `marvelrivals-forge`, version attr `mrforge.__version__` = `0.1.0`, `requires-python >=3.10`, dep `Pillow>=10`, script `mrforge = mrforge.cli:main`); `src/mrforge/{__init__,__main__,cli,util}.py`; `mrforge.cmd` (DisableDelayedExpansion; `.venv` python, else `PYTHONPATH=src`); `tests/run_tests.py` (unittest discovery). CLI contract: every command prints one JSON object `{ok, command, version, data, errors[], warnings[], gaps[]}`; exit 0 ok, 1 failure, 2 usage, 3 environment; `--pretty`; subprocesses always argv lists | done | T01 | `python tests/run_tests.py` green; `mrforge.cmd version` prints valid JSON with `0.1.0`; a test runs the CLI from a temp dir whose path contains a space, `!` and `(` | suite green; `mrforge.cmd version` JSON 0.1.0; tests run CLI and `mrforge.cmd` from a path with space, `!`, `(` |
| T03 | `home.py`: forge home = `MRFORGE_HOME` or `<forge root>/.mrforge`; subdirs `tools/ cache/usmap cache/index logs/ receipts/`; `config.json` (game path, projects root, deploy prefix); quiet invocation log | done | T02 | unit tests with a temp `MRFORGE_HOME` | unit tests with temp MRFORGE_HOME (layout, config, log) |
| T04 | `game.py` + `mrforge game`: resolve game by `--game` > `MRFORGE_GAME` > config > Steam `libraryfolders.vdf` + `appmanifest_2767030.acf`; derive `paks_dir`, `mods_dir` (`Paks/~mods`), `win64_dir`; parse `MarvelGame/version.json` (`version`, `changelist`); detect loader (`win64/dsound.dll` + `win64/plugins/*.asi`), mod-manager markers (`vortex.deployment.*.json`, `__folder_managed_by_vortex`, `*_loadOrder.json`), game running (`Marvel-Win64-Shipping.exe`) | done | T03 | unit tests on a synthetic game tree; live: `mrforge game` reports changelist `4042190`, loader present | unit tests on synthetic Steam/game trees; live: changelist 4042190, loader + bypass present, Vortex markers |
| T05 | `tools.lock.json` + `tools.py` + `mrforge setup [--from <dir>...] [--offline]`. Lock entry: `name, repo, tag, asset, asset_sha256, exe, exe_sha256, license, probe argv, probe expect`. Pins: retoc-rivals-cli `v3.11.1` (natimerry/repak-rivals, `retoc-rivals-cli-x86_64-pc-windows-msvc.zip`), UAssetTool `v1.5.9` (X-zant/UAssetToolRivals, `UAssetTool-win-x64.zip`), fmodel-mcp `v1.2.0` (MayankS-Code/fmodel-mcp, `fmodel-mcp-1.2.0-win-x64.zip`), ueformat-blender `v10` (h4lfheart/UEFormat, `ueformat-blender.zip`). Resolution order per tool: installed copy with matching `exe_sha256` -> copy found under `--from` with matching `exe_sha256` -> download the release asset, check `asset_sha256`, unpack to `.mrforge/tools/<name>/<tag>/`. Never run an installer. Fill hashes from the upstream `.sha256` assets and by hashing the downloaded files; cross-check the exe hashes in `LOCAL.md` | done | T03 | unit tests with file-URL fake releases (good hash, bad hash, offline); live: `mrforge setup --from <third-party collection>` then probes return `retoc-rivals-cli 3.11.1` and `UAssetTool v1.5.9` | file-URL fake releases (good/bad asset hash, bad exe hash, offline, --from, unsafe zip); live `setup --from`: 4 tools, probes 3.11.1 / v1.5.9; release zips re-downloaded, exe hashes equal lock |
| T06 | `sync.py` + `mrforge sync`: list `SpaceDepot/rivals-depot` `usmap/` (GitHub contents API, generic User-Agent `mrforge`); pick the file whose build number equals the installed changelist (name pattern `5.3.2-<build>+++depot_marvel+S<season>_release-Marvel.usmap`); cache in `.mrforge/cache/usmap/` with SHA-256; no exact build -> failure `USMAP_BUILD_MISMATCH` naming the nearest lower build and `--allow-nearest`. Fetch `AES.json` `mainKey` into `.mrforge/keys.json`; the key never appears in output or logs. Offline reuses the cache | done | T04 | unit tests with an injected fetcher (match, mismatch, offline, key redaction); live: cached usmap SHA-256 equals the value in `LOCAL.md` | injected-fetcher tests (match, mismatch+nearest, offline, key redaction in output and log); live usmap SHA-256 726e3d5b...83ad = LOCAL.md |
| T07 | `doctor.py` + `mrforge doctor`: sections `payload`, `toolchain`, `game`, `data`, `routes`; each check `{id, status ok/warn/fail/skip, detail, fix}`. Exit 0 only when payload, toolchain and game have no `fail`. Routes: `texture`/`material` need retoc + UAssetTool + matching usmap; `mesh-export` needs fmodel-mcp + Blender >= 4.2 + ueformat-blender + Oodle DLL; `mesh-build` needs UE 5.3.2 (Epic `LauncherInstalled.dat` / registry) and is `unavailable`, not `fail`, when missing. Warn: loader absent; encrypted, obfuscated or stripped mods present in `~mods` (list them) | done | T05, T06 | unit tests on synthetic trees for each failure name; live: exit 0, `mesh-build: unavailable` | synthetic failure tests; live exit 0; mesh-build now `available` (UE 5.3.2 installed and detected) |
| T08 | `mrforge capabilities` / `guide`: generated from the argparse registry plus route availability | done | T07 | test: every registered subcommand appears; no hand-kept list in the module | test: capabilities == parser leaves; no hand-kept list |
| T09 | Knowledge data in `src/mrforge/knowledge/`: `facts.json` (`id, statement, tier verified-local/upstream-doc/reported, source, date`) seeded from "Verified ground truth"; `routes.json`; `errors.json`; `asset-layout.md`, `texture-route.md`, `material-route.md`, `packaging.md`, `loading-and-anticheat.md`, `tools.md`; `mrforge knowledge [topic]`, `mrforge facts [--grep]` | done | T02 | test: every fact has tier + source; every route names existing commands | tests: every fact has tier+source, routes name real commands, docs exist, signatures compile |
| T10 | Catalog: `knowledge/skins.json` converted from `natimerry/repak-rivals` `repak-gui/src/data/character_data.json` (Apache-2.0; record commit SHA and date in `knowledge/SOURCES.json`, notice in `THIRD-PARTY.md`). `mrforge hero list/find`, `skin list <hero>`, `skin find <text>`; `catalog sync` writes an override layer in `.mrforge/cache/` | done | T09 | tests: lookups by name and id; hero id = first 4 digits of a 7-digit skin id for every row | 447 rows from commit 01fdcfd (2026-04-03); hero id = first 4 digits for every row; SOURCES.json + THIRD-PARTY.md |
| T11 | Installed-truth index + `mrforge index`, `mrforge skin inspect <skinId>`: enumerate packages under `Marvel/Content/Marvel/Characters/` from the vanilla containers into `.mrforge/cache/index/<changelist>.json` (first capture real output of `UAssetTool list_iostore <paks> --filter ...`; if it cannot list vanilla-only with paths, use `extract_iostore_legacy --list`-style output or fmodel-mcp search with its `archive` field). `skin inspect`: meshes, materials, textures (dims, pixel format, mips), physics assets, material slots and tags from `skeletal_mesh_info`, assets shared from another skin id, and which deployed mods override each package | done | T05, T06, T10 | unit tests on synthetic tool output; live: `skin inspect 1061303` shows `SK_1061_1061303` + `_Lobby`, 18 material slots, `T_1061303_Body_01_{D,N,ORM,S}` | A4 verified: list_iostore 4.9 s for 314,521 pkgs; live `skin inspect 1061303`: SK_1061_1061303 + _Lobby, 18 slots, T_1061303_Body_01_{D,N,ORM,S} |
| T12 | `mods.py`: `mrforge mods list` (recursive scan of `~mods`; per triple the package list from `retoc-rivals-cli manifest --filters`, flags from `info`; cached by size + mtime) and `mrforge conflicts [--project]` | done | T05, T04 | unit tests with a retoc shim; live: the body-reshape mod named in `LOCAL.md` lists 7 packages under `1061/1061303` | retoc-shim tests; live: body-reshape mod lists 7 packages under 1061/1061303 |
| T13 | `project.py`: `mrforge new "<Name>" --skin <id or name> --kind texture[,material] [--out]` (default `<forge>/projects/<slug>/`), manifest `mrforge.json` (`id, name, version, hero, skin, kinds, game_changelist, adds[]`), layout `vanilla/ work/textures work/materials build/ dist/`, `CHANGELOG.md`; `mrforge bump` | done | T10 | unit tests: scaffold, bump, slug rules for names with spaces and punctuation | scaffold/bump/slug tests |
| T14 | `extract.py` + `mrforge extract [--textures <glob>] [--materials] [--all]`: `UAssetTool extract_iostore_legacy <paks> <project>/vanilla --filter <paths>` (vanilla containers only); textures to `work/textures/*.png` via `batch_extract_texture --usmap`; materials to `work/materials/*.json` via `to_json`; `vanilla.lock.json` records per package file hashes, changelist, dims, pixel format, mip count | done | T11, T13 | unit tests with a UAssetTool shim; live: `T_1061303_Body_01_D` extracts as 2048x2048, `PF_DXT1`, 12 mips | shim tests; live: T_1061303_Body_01_D 2048x2048 PF_DXT1 12 mips |
| T15 | `tex.py` (Pillow): `tex list`, `tex hue --shift`, `tex tint --color --strength`, `tex levels`, `tex overlay <png>`, `tex replace <name> <png>`, all with optional `--mask`; ops stored in `work/ops.json` and re-applied from the vanilla PNG on every build (idempotent). Suffix rules as data: `_D` colour, `_N` normal (colour ops refused unless `--force`), `_ORM`/`_S`/`_M` channel-packed (warn). `tex sheet` writes `build/preview/sheet.png` (vanilla beside edited) for visual review | done | T14 | unit tests on synthetic images: op determinism, mask, `_N` refusal, sheet dimensions | tests: determinism, alpha kept, mask, _N refusal, packed warn, hand-edit conflict, sheet dims; live sheet looked at |
| T16 | `mat.py`: spike first, then `mat list` / `mat set <MI> <param> <value>` on UAssetTool full JSON. Spike: `to_json` -> `from_json` of one vanilla `MaterialInstanceConstant`, pack, extract again, compare parameter values; then change one vector parameter and confirm it survives the round trip. Study the installed material-only recolor named in `LOCAL.md` for which parameters real mods change | done | T14 | live: round trip keeps all parameters, edited value reads back; unit tests on a synthetic JSON shaped like the captured structure. If `from_json` cannot round-trip, mark `blocked` with the tool error and ship v0.1.0 texture-only | A2 verified: 26/26 params survive to_json->from_json, .uexp byte-identical, edit reads back; zero-colour set needs header drop (D15); live V-MAT reads values back from the packed mod |
| T17 | `build.py` + `mrforge build`: re-apply ops; `inject_texture <vanilla uasset> <png> <staging uasset> --usmap` (default mip-chain mode) for each changed texture; `from_json` for changed materials; staging `build/<ModName>/Marvel/Content/...` holds changed packages only; `retoc-rivals-cli pack build/<ModName> --output dist` (output name comes from the input folder: `<ModName>_9999999_P.{pak,utoc,ucas}`); never `--obfuscate`, `--strip` or encryption; `dist/receipt.json` (input hashes, tool versions and hashes, changelist, usmap hash, argv) | done | T15, T16 | unit tests with shims (only changed packages staged, receipt complete); live: one-texture mod builds to 1 package with flags `Compressed, Indexed` | shim tests (only changed packages staged, receipt complete); live: 1-texture mod -> 1 package, flags Compressed, Indexed |
| T18 | `validate.py` + `mrforge validate` on the built triple: `V-NAME` (three files, `_9999999_P`), `V-FLAGS` (not encrypted), `V-PATHS` (every package exists in the vanilla index for this changelist unless listed in manifest `adds`), `V-LEAK` (no Skeleton, PhysicsAsset or placeholder package unless declared), `V-TEX` (round-trip via `extract_iostore_legacy --mod`: pixel format equals vanilla, mips present, dims differ = warning), `V-STALE` (receipt changelist equals installed), `V-CONFLICT` (deployed mods touching the same packages = warning with names). Result tiers: `static`, `build`, `package` pass/fail; `load`, `gameplay` = `not_run` | done | T17, T12 | unit tests: one failing case per rule; live: spike mod passes, a deliberately misspelled path fails `V-PATHS` | one failing test per rule; live: selftest + material mod pass all rules |
| T19 | `package.py` + `mrforge package`: `dist/<Name>-<version>.zip` holding only the triple (plus `README.txt` when the manifest has a description), deterministic (sorted entries, fixed timestamps); print SHA-256 | done | T18 | test: two builds give identical bytes; zip listing has exactly the expected names | test: two packages byte-identical; listing exact |
| T20 | `deploy.py` + `mrforge deploy [--prefix ZZZ]` / `undeploy` / `deploy --status`: copy the triple to `<mods_dir>/<prefix>-mrforge-<id>/`; refuse while the game runs; receipt in `.mrforge/receipts/<id>.json`; undeploy removes only receipt-listed files whose hash still matches; never touches any other folder | done | T18, T04 | unit tests on a synthetic tree (foreign files untouched, refusal when running); live: recursive listing of `~mods` is identical before deploy and after undeploy | synthetic tests (foreign files untouched, running refusal, changed file kept); live: ~mods listing (986 entries) identical before deploy / after undeploy |
| T21 | `mrforge selftest texture`: temp project -> extract one texture -> hue op -> build -> validate -> package, no deploy; the real-toolchain smoke run. Start `VALIDATION.md` with the tier table for this run | done | T19 | live: exit 0, `static/build/package` pass, `load/gameplay` listed `not_run` | live: exit 0, static/build/package pass, load/gameplay not_run, 16 s; VALIDATION.md started |
| T22 | `mrforge check-load <id>`: verifies deployed files + loader, scans the newest game log and `Galacta.log` for signatures in `errors.json`, prints what to look at in game; `--confirm "<note>"` records owner-observed load/gameplay results in the project | done | T20 | unit tests on synthetic logs; live after the owner's first in-game check | synthetic-log tests incl. --confirm; live scan of newest game log + Galacta.log. Owner in-game check still pending |
| T23 | `mrforge plan "<request>"`: router over `routes.json` -> route, exact command sequence, documents, things to avoid, availability from doctor. Routes: recolor/retexture/logo/skin tone -> `texture`; glow/tint/roughness parameter -> `material`; new model/body shape/outfit swap -> `mesh` (v0.2); jiggle/physics -> `physics` (not in v0.1, says so) | done | T09, T07 | test table: at least 12 sample requests map to the expected route | 15-request table maps to expected routes |
| T24 | Agent and repo docs: `AGENTS.md` (runbook: sources of truth, module map, loop, boundaries), `CLAUDE.md` (pointer), `skills/marvelrivals-forge/SKILL.md` (cold start: doctor -> plan -> skin inspect -> new -> extract -> edit -> `tex sheet` and look at it -> build -> validate -> package -> deploy -> check-load), `README.md`, `SECURITY.md`, `THIRD-PARTY.md`, `CHANGELOG.md`, `DECISIONS.md` (from the section below), `VALIDATION.md` | done | T23 | test: version mirrors agree (`__init__`, CHANGELOG top entry, STATE, SKILL.md); grep finds no drive letters or user names in tracked files | tests: version mirrors agree; no drive letters/user names in tracked files |
| T25 | `Install.ps1`, `Uninstall.ps1`, `START-HERE.bat`: `.venv`, `pip install -e .`, one user-PATH shim for `mrforge`, optional `-Skills` copy into detected agent skill folders; second run converges; uninstall removes only what install added; `.mrforge/` and `projects/` survive both | done | T24 | live: run install twice -> one PATH entry, `mrforge version` works from another folder; uninstall then reinstall keeps a dummy project | live: two installs -> 1 PATH entry, `mrforge version` from another folder; uninstall removes entry; reinstall keeps dummy project and .mrforge |
| T26 | `.github/workflows/ci.yml`: tests on ubuntu + windows, Python 3.10 and 3.13; CLI smoke (`capabilities`, `plan`); windows `toolchain` job runs `mrforge setup` for real and the version probes; `install` job runs the installer twice and the uninstaller | done | T25 | local suite green; after T28, CI green on the pushed SHA | workflow written (tests matrix, toolchain, install, release-archive); local suite green; CI result recorded at T28 |
| T27 | `tools/build_release.py`: `artifacts/MarvelRivals-Forge-<ver>.zip` from `git ls-files` only, deterministic; `SHA256SUMS`, `manifest.json`, build receipt | done | T26 | built twice -> identical bytes; archive has no `LOCAL.md`, `.mrforge/`, `projects/` | built twice -> identical SHA256SUMS; 72 tracked files; no LOCAL.md/.mrforge/projects |
| T28 | Publish v0.1.0: create public GitHub repository `MarvelRivals-Forge` under the owner account (MIT); push `main`; wait for every check on that exact SHA; query Dependabot, code-scanning and secret-scanning alerts; tag `v0.1.0`; release from the validated tag with the T27 assets; download and re-hash the published asset | pending | T21, T27 | `gh run list` green on the tagged SHA; alert queries return zero open (or are named unknown); published asset hash equals local | - |
| T29 | Register: one row in the bundle's companion registry and in the `ai-tooling-stack` forge table (bundle repo, its own commit and procedure); `app_paths.py --fix`; row in the private `PROJECTS.md`; verdict lines in the private `SAFE-TOOLS.md` for retoc-rivals-cli, UAssetTool, fmodel-mcp, ueformat-blender and the rivals-depot mapping source | pending | T28 | `mrforge doctor` runs by name from any folder; `companion_registry.py --verify` lists the forge | - |
| T30 | v0.2 mesh export: `fmcp.py` minimal MCP stdio client for `FModel.Mcp.exe --config <generated json>` (see ground truth for the protocol); `mrforge mesh export [--lobby]` -> `work/mesh/vanilla/*.uemodel` + material JSON + PNG. Override handling: when `fmodel_search_assets` shows the package also in a non-`pakchunk*` archive, export from a temporary vanilla view (hardlinks of the top-level game containers in a forge-owned folder on the game's volume, deleted in `finally`); hardlink failure -> `VANILLA_VIEW_UNAVAILABLE` naming the overriding mod | pending | T28 | unit tests with a fake MCP server script; live: `SK_1061_1061303` exports in under 60 s and comes from `pakchunkCharacter-Windows` even while the override mod is deployed; no view folder left behind | - |
| T31 | v0.2 Blender leg: `mrforge mesh blend` (headless: add the ueformat-blender folder to `sys.path`, `register()`, `bpy.ops.uf.import_uemodel(files=[{"name": ...}], directory=...)`, save `.blend`), `mesh fbx` (`add_leaf_bones=False`), `mesh check` (bone names and hierarchy equal vanilla, material slot names and order equal vanilla, vertex groups are bones, triangle count) | pending | T30 | live: LOD0 of `SK_1061_1061303` imports as 81410 vertices, 488 bones, 18 material slots; `mesh check` passes on the unmodified round trip and fails after a slot is renamed | - |
| T32 | v0.2 UE spike (needs UE 5.3.2, see Open questions): detect 5.3.2; `mrforge ue init` creates a project named exactly `Marvel` with IoStore off and plugins KawaiiPhysicsRivals `v2.1.0` and RivalsMeshMaterialManager `v1.2.0`; headless Python import of the FBX to the vanilla package path bound to placeholder Skeleton and material assets at the vanilla paths; headless cook; collect `Saved/Cooked/Windows/Marvel/Content/...` minus placeholders; `retoc-rivals-cli pack` (with hidden-material patching if the vanilla mesh has hidden slots); `mrforge validate`; owner checks in game. Write every verified step and failure into `knowledge/mesh-route.md` and `facts.json` | pending | T31, owner installs UE 5.3.2 | live: the cooked, packed mesh passes `validate` and the owner confirms it renders in lobby and match; otherwise `blocked` at the exact failing step with its output | - |
| T33 | v0.2 productize: `mrforge mesh build`, rules `V-MESH` (no skeleton/physics leak, material tags equal vanilla `skeletal_mesh_info`, lobby mesh paired), `selftest mesh`, route docs, release `v0.2.0` by the T27/T28 procedure | pending | T32 | selftest mesh passes live; CI green; release verified | - |
| T34 | Optional v0.2.x physics route: wrappers over `retoc-rivals-cli fix-kawaii-physics` and `--kawaii-options-json` with a tuning JSON per skin | pending | T33 | live: tuned physics asset passes `validate`; owner confirms in game | - |

## Architecture

```
MarvelRivals-Forge/
  src/mrforge/        cli, home, game, tools, sync, doctor, catalog, index, mods, project, extract,
                      tex, mat, build, validate, package, deploy, plan, (v0.2: fmcp, mesh, ue)
  src/mrforge/knowledge/   facts.json routes.json errors.json skins.json SOURCES.json *.md
  src/mrforge/blender/     headless Blender scripts (v0.2)
  skills/marvelrivals-forge/SKILL.md
  tests/              offline unit tests, synthetic fixtures, tool shims; live tests behind --live
  tools/build_release.py
  tools.lock.json     pinned upstream tools with hashes
  .mrforge/           (ignored) tools, caches, keys, receipts, logs
  projects/           (ignored) mod projects
```

Data flow for the default route (no Unreal Editor):
vanilla containers -> `UAssetTool extract_iostore_legacy` -> legacy `.uasset/.uexp/.ubulk/.uptnl` -> PNG / JSON
-> edit (recorded ops) -> `inject_texture` / `from_json` -> staging tree -> `retoc-rivals-cli pack`
-> `<Name>_9999999_P.{pak,utoc,ucas}` -> validate (round-trip) -> zip -> deploy folder in `~mods`.

Evidence tiers reported separately on every build: `static`, `build`, `package`, `load`, `gameplay`.
The forge can prove the first three; the last two need the game running and are recorded only from the
owner's confirmation.

## Verified ground truth (observed 2026-11-15 on the build machine)

Game and layout
- Install has `MarvelGame/version.json` with `version` and integer `changelist`; changelist equals the build
  number in the mapping file name. Engine 5.3.2; CUE4Parse profile `GAME_MarvelRivals`.
- Containers: `MarvelGame/Marvel/Content/Paks/*.{pak,utoc,ucas,sig}` (39 IoStore containers incl. `global`,
  589,956 packages). Mods: `Paks/~mods/**`, subfolders allowed (the mod manager deploys one folder per mod,
  ordered by an `AAA-`.. prefix).
- Skin assets: `Marvel/Content/Marvel/Characters/<hero 4 digits>/<skin 7 digits>/` with
  `Meshes/SK_<hero>_<skin>.uasset`, `Meshes/SK_<hero>_<skin>_Lobby.uasset`, `Materials/MI_<skin>_<Part>.uasset`,
  `Materials/Lobby/...`, `Textures/T_<skin>_<Part>_{D,N,ORM,S,M}.uasset`, `Post_<skin>_Physics.uasset`,
  `Post_<skin>_Lobby_Physics.uasset`. A skin's materials can reference textures of another skin id of the same
  hero (seen: skin 1061303 pulling `1061001` textures), so editing a shared texture changes every skin using it.
- Mod file name: `<Name>_9999999_P.{pak,utoc,ucas}`; mount point `../../../`; community mods on disk show
  `container_flags: Compressed | Indexed`, Oodle.
- Loading needs the ASI loader + UTOC signature bypass in `Binaries/Win64` (present on the build machine).

retoc-rivals-cli 3.11.1
- `info <utoc>`, `manifest <utoc> [--filters]`, `unpack <utoc> --output <dir> --game-paks-dir <paks>`,
  `pack <rawdir> --output <dir>` (default Oodle, appends `_9999999_P`, output name = input folder name),
  `pack-dir`, `fix-kawaii-physics`. Options seen in `--help`: `--no-mod-suffix --compression --kawaii-physics
  --kawaii-physics-usmap --keep-existing-chains --kawaii-options-json --patch-default-hidden-mats
  --default-hidden-material-bitmaps --game-paks-dir --full-iostore-check --obfuscate --strip`.
- Upstream changelog 3.11.1: since Season 11 the game's anti-cheat reports encrypted, obfuscated and stripped
  mods. The forge therefore emits plain containers only and flags such mods in `doctor`.
- Release asset hash (upstream `.sha256`): `4d4f06db77b12f53000f082f324ac6e40f47b4f08e126029d70c56e8eaeb12a4`.

UAssetTool 1.5.9
- `extract_iostore_legacy <paks> <out> --filter <substr...> [--with-deps] [--mod <utoc|dir>]`: without `--mod`
  it loads only the top-level game containers (vanilla, ignores `~mods`); 1 texture in about 6 s.
- First extraction downloads `oo2core_9_win64.dll` next to the exe (it did so on the build machine).
- `extract_texture <uasset> <png> --usmap`, `inject_texture <base> <image> <out> --usmap` (pixel format kept,
  full mip chain: `.uasset .uexp .ubulk .uptnl`), `batch_extract_texture`, `batch_inject_texture`,
  `to_json` / `from_json`, `batch_detect`, `skeletal_mesh_info <uasset> <usmap>` (material slots, slot names,
  gameplay tags such as `MaterialTag.*`), `list_iostore`, `is_iostore_encrypted`, `create_mod_iostore`.
- Proven end to end: vanilla `T_1061303_Body_01_D` (2048x2048, `PF_DXT1`, 12 mips) -> PNG -> edited -> injected
  -> `retoc pack` -> 1 package, 4 chunks, not encrypted -> extracted back from the mod -> PNG differs from the
  edited input by RMSE 0.27% (block-compression loss only).

fmodel-mcp 1.2.0 (CUE4Parse 1.2.2)
- Stdio MCP server: newline-delimited JSON-RPC 2.0. `initialize` (protocolVersion `2025-11-25`), then
  `notifications/initialized`, then `tools/call`; results arrive in `result.structuredContent`.
- Config JSON (`--config`): `inputRoots[]`, `outputRoot`, `oodleLibrary`; unknown fields are rejected; paths
  given to tools must be absolute and inside an input root; symlinks and junctions are refused.
- `fmodel_open_game {options:{directory, game:"GAME_MarvelRivals", mappingsPath, aesKeys:{<32 zeros>: key}}}`
  mounted 570 archives (it also mounts `~mods`). `fmodel_search_assets` returns one hit per archive with an
  `archive` field. `fmodel_start_export {sessionId, request:{paths[], mode:"converted", meshFormat:"UEFormat",
  textureFormat:"Png"}}`; poll `fmodel_job_status` field `state` until it leaves
  `queued/running/finalizing/cancelling`; `fmodel_close_game` before closing stdin (closing early cancels).
- `SK_1061_1061303` exported in 17 s: `.uemodel`, 17 material JSON files, 83 PNG textures. With an
  override mod deployed the export came from the mod, not vanilla.
- Opening a folder of loose legacy packages (UAssetTool output) mounts, but mesh conversion fails with a null
  reference. Do not use loose folders as a vanilla source.

Blender 5.3.0 + ueformat-blender 0.10.0
- Headless import works without installing the add-on: put its parent folder on `sys.path`, import
  `io_scene_ueformat`, call `register()`, then `bpy.ops.uf.import_uemodel`. Result for the mesh above: one mesh
  (81,410 vertices, 18 materials, 336 vertex groups) and one armature (488 bones); FBX export works.

Data sources
- Mappings and key: `SpaceDepot/rivals-depot` (`Mappings.json`, `usmap/`, `AES.json` field `mainKey`); the same
  source retoc downloads from. A file for build 4042190 (S11.0) exists.
- Hero/skin table: `natimerry/repak-rivals` `repak-gui/src/data/character_data.json` (fields `name, id, skinid,
  skin_name`; about 94 KB; Apache-2.0).
- Mesh tooling for UE 5.3.x: `X-zant/KawaiiPhysicsRivals` v2.1.0 (MIT, prebuilt for 5.3.2),
  `X-zant/RivalsMeshMaterialManager` v1.2.0 (Apache-2.0, `-Win64.zip`); retoc and UAssetTool read its
  per-slot tag and hidden-material carrier during packing.

## Decisions

| # | Chosen | Rejected | Why |
|---|---|---|---|
| D1 | Python CLI `mrforge` (stdlib + Pillow), same shape as the newest sibling forge | Rust/C# CLI; MCP-first forge | Matches the owner's forge standard and existing forges; the heavy lifting is already in upstream binaries; CLI + JSON works in a cold session |
| D2 | Tools pinned in `tools.lock.json` with hashes and fetched by `mrforge setup` into `.mrforge/tools/` | Committing tool binaries to the repository; relying on PATH | Upstream tools change with every game season (three releases in three weeks); a lock gives reproducibility without a 100+ MB history and makes updates one reviewed diff. `--from` adopts copies already on disk, so nothing is downloaded twice |
| D3 | Default route is editor-free: texture and material edits via UAssetTool + retoc | Making every skin mod go through Unreal Editor | Proven end to end today in seconds, fully scriptable, no 40+ GB dependency. It covers recolours, retextures, decals, skin-tone and material-parameter mods |
| D4 | retoc-rivals-cli is the packer; UAssetTool is the extractor/editor | UAssetTool `create_mod_iostore` as packer; repak-gui | retoc is the community's reference packer, has the KawaiiPhysics and hidden-material fixes and a `.sha256` per release. UAssetTool stays as the fallback packer if a retoc release breaks |
| D5 | Vanilla assets always come from `UAssetTool extract_iostore_legacy` without `--mod` | Reading through fmodel-mcp for textures; unpacking installed mods as a base | It ignores `~mods` by design, so a deployed mod can never leak into a new mod's base |
| D6 | Mesh export uses fmodel-mcp driven over stdio by a small built-in client, with a temporary hardlink vanilla view only when a mod overrides the target | Own CUE4Parse exporter; loose-folder conversion; asking the owner to disable mods | fmodel-mcp already works on this game and build; a custom exporter is a second compiled component to maintain (kept as the escalation path); loose folders fail (tested) |
| D7 | Mesh build goes through Unreal Engine 5.3.2 headless (Python import + cook) and ships in v0.2 behind a spike | Shipping mesh support unverified in v0.1; binary patching of cooked skeletal meshes | UE 5.3.2 is not installed, so nothing about that leg can be verified today; no existing tool injects geometry into cooked meshes |
| D8 | Plain output only: no obfuscation, encryption or stripping, and `validate` fails on an encrypted container | Exposing retoc's `--obfuscate` / `--strip` | Since Season 11 the game reports such mods (upstream changelog) |
| D9 | The forge never installs or updates the loader/bypass; `doctor` detects and reports it | Bundling the ASI loader | It is distributed through the mod site and managed by the owner's mod manager; it is already installed |
| D10 | `deploy` copies into its own `ZZZ-mrforge-<id>` folder in `~mods` with a receipt; `package` makes a zip the mod manager can import | Writing into the mod manager's staging; editing its load-order file | Keeps the mod manager's state untouched and makes undeploy exact |
| D11 | Hero/skin table is a vendored snapshot with provenance plus an installed-truth index built from the game | Hand-written table; scraping a wiki | The snapshot gives names; the index gives what really exists in this build, and wins on conflict |
| D12 | Usmap must match the installed changelist exactly by default | Always taking the newest mapping | A wrong mapping reads unversioned properties wrongly without an error |
| D13 | Machine paths live in ignored `LOCAL.md`; tracked files stay publishable | Paths in PLAN/STATE | The repository is public |
| D14 | Releases: v0.1.0 = texture + material routes; v0.2.0 = mesh; physics after that | One big release | Value ships as soon as the verified route is productized; the unverified leg cannot delay it |

## Assumptions (each with its fastest check)

| # | Assumption | Fastest check |
|---|---|---|
| A1 | A plain texture mod built this way loads and shows in game on Season 11 with the installed loader | T20 deploy the T21 mod (a strong hue shift on one body texture), owner opens the hero in the lobby |
| A2 | `UAssetTool to_json`/`from_json` round-trips `MaterialInstanceConstant` assets of this build | T16 spike: one material, two commands, compare parameters |
| A3 | Among mods providing the same package, the one in the later-sorted folder wins, so the `ZZZ-` prefix overrides mod-manager folders | Deploy the A1 mod while a mod touching the same texture is deployed; if it does not win, `V-CONFLICT` becomes an error telling the owner to disable the other mod |
| A4 | `UAssetTool list_iostore` (or an equivalent listing) can enumerate vanilla package paths fast enough to index `Characters/` | Run it once with `--filter Characters/1061/` and time it (T11) |
| A5 | Textures injected at a different resolution than vanilla are accepted by the game | Build one mod at half resolution, owner checks in game; until then `tex replace` resizes to vanilla dims by default |
| A6 | A cooked mesh can keep vanilla materials by pointing at placeholder assets created at the vanilla paths and left out of the pack | T32 spike step 2; the KawaiiPhysics plugin documents the same placeholder pattern for physics references |
| A7 | UE 5.3.2 can import FBX and cook headless through the Python commandlet for this project layout | T32 spike step 1 on an empty `Marvel` project |
| A8 | The hardlink vanilla view is accepted by fmodel-mcp and leaves no residue | T30 live test; fallback is the named error |
| A9 | The game log or `Galacta.log` carries a usable signal for a mod that failed to mount | Compare logs of a run with a deliberately corrupt mod deployed (owner run); if nothing shows, `check-load` stays a checklist |
| A10 | CI runners can download the pinned release assets | T26 `toolchain` job |

## Risks

- Game patches (roughly every two weeks in season) change the changelist: mappings, tools and vanilla hashes go
  stale. Mitigation: exact-build usmap rule, `V-STALE`, `doctor` build check, a `tools.lock.json` bump as a
  named maintenance step, receipts that record the build a mod was made for.
- Upstream tools are small community projects; a release can disappear or change behaviour. Mitigation: hashes,
  adoption from local copies, UAssetTool as second packer, the release ZIP of each tool kept in `.mrforge/tools`.
- Anti-cheat policy can tighten again (it did in Season 11). Mitigation: plain containers only, `doctor`
  warning for flagged mod types, facts tiered `reported` until verified, no memory-injection components in the
  forge at all.
- The mesh route depends on a 40+ GB engine the owner must install and on steps that could not be tested;
  the T32 spike may end `blocked`. v0.1.0 does not depend on it.
- Shared textures: a retexture can change other skins of the same hero. Mitigation: `skin inspect` marks
  shared assets and `build` warns when a changed package lives under another skin id.
- The vanilla view uses hardlinks to multi-GB game files; a crash could leave links that keep old data alive
  after a game update. Mitigation: per-process folder, removal in `finally`, `doctor` check for leftovers.
- The first run of UAssetTool downloads the Oodle DLL itself; offline first runs fail. Mitigation: `setup`
  records its presence and `doctor` names the fix.
- Load and gameplay tiers cannot be automated; a mod can pass `validate` and still look wrong in game.
  Mitigation: `tex sheet` visual review before build, tiers reported honestly, `check-load --confirm`.

## Open questions for the owner

1. RESOLVED 2026-11-15: UE 5.3.2 installed by the owner; `mrforge doctor` detects it (mesh-build available).
2. Repository name and visibility: default is public `MarvelRivals-Forge` under the owner account, MIT.
3. Mod projects default to `<forge>/projects/` (ignored by Git). Use another root instead?
4. T29 edits the bundle repository (registry row and forge table). Do it in the build session, or leave it?
5. Who runs the first in-game check (A1, A3)? The forge stops at the package tier until someone launches the game.
6. Is the physics route (T34) wanted, or are textures, materials and meshes the whole scope?
