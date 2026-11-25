# Third-party material

## Vendored data

| File | Source | License | Notes |
|---|---|---|---|
| `src/mrforge/knowledge/skins.json` | [natimerry/repak-rivals](https://github.com/natimerry/repak-rivals) `repak-gui/src/data/character_data.json`, commit `01fdcfd14e9d21589eb844ca161cc475df2faa8c` (2026-04-03) | Apache-2.0 | Reduced to skin id, hero id, hero name, skin name. Provenance in `knowledge/SOURCES.json`. |

Apache License 2.0 notice for the data above: Licensed under the Apache License, Version 2.0; you may obtain a
copy at https://www.apache.org/licenses/LICENSE-2.0. Distributed on an "AS IS" basis, without warranties or
conditions of any kind.

## Formats and constants from other projects

| Where | Source | License | Notes |
|---|---|---|---|
| `src/mrforge/snd.py` `WEM_HEADER` (96-byte Wwise PCM .wem header) | [oZanderr/Rivals-Toolkit](https://github.com/oZanderr/Rivals-Toolkit) `src-tauri/src/audio/wem.rs` | MIT or Apache-2.0 | The header layout of a PCM .wem the game ships; the bank code in `snd.py` is written from the Wwise bank format, not copied. |

MIT notice for the header above: Copyright (c) 2026 oZanderr. Permission is hereby granted, free of charge, to any
person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the
Software without restriction, including without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions: The above copyright notice and this permission notice
shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT
WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

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
