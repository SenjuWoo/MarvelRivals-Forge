# Third-party material

## Vendored data

| File | Source | License | Notes |
|---|---|---|---|
| `src/mrforge/knowledge/skins.json` | [natimerry/repak-rivals](https://github.com/natimerry/repak-rivals) `repak-gui/src/data/character_data.json`, commit `01fdcfd14e9d21589eb844ca161cc475df2faa8c` (2026-04-03) | Apache-2.0 | Reduced to skin id, hero id, hero name, skin name. Provenance in `knowledge/SOURCES.json`. |

Apache License 2.0 notice for the data above: Licensed under the Apache License, Version 2.0; you may obtain a
copy at https://www.apache.org/licenses/LICENSE-2.0. Distributed on an "AS IS" basis, without warranties or
conditions of any kind.

## Tools fetched at setup time (not redistributed in this repository)

| Tool | Source | License |
|---|---|---|
| retoc-rivals-cli | https://github.com/natimerry/repak-rivals | Apache-2.0 / MIT (license files ship in the release) |
| UAssetTool | https://github.com/X-zant/UAssetToolRivals | GPL-3.0 |
| fmodel-mcp | https://github.com/MayankS-Code/fmodel-mcp | GPL-3.0 |
| UEFormat (Blender importer) | https://github.com/h4lfheart/UEFormat | GPL-3.0-or-later |
| RivalsMeshMaterialManager (UE 5.3 plugin) | https://github.com/X-zant/RivalsMeshMaterialManager | Apache-2.0 |

These run as separate programs; mrforge calls them as subprocesses and does not link to them.

## Data fetched at run time

Mapping files (`.usmap`) and the game AES key come from https://github.com/SpaceDepot/rivals-depot and are stored
only in the local, git-ignored `.mrforge/` folder.
