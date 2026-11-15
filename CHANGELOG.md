# Changelog

## 0.1.0 - 2026-11-15

First release: texture and material routes, editor-free.

- `mrforge` CLI with a JSON contract (`ok, command, version, data, errors, warnings, gaps`; exit 0/1/2/3).
- Setup of pinned tools (retoc-rivals-cli 3.11.1, UAssetTool 1.5.9, fmodel-mcp 1.2.0, UEFormat Blender v10) from
  GitHub releases or existing copies, verified by SHA-256.
- Game discovery through Steam, build/changelist, ASI loader and signature-bypass detection, installed-mod scan
  with encrypted/obfuscated/stripped flags and conflicts.
- Exact-build mapping download (`sync`), vanilla package index (`index`), hero/skin name table, `skin inspect`
  (meshes, material slots and tags, textures with format and mips, assets shared with other skins, overriding mods).
- Projects: `new`, `extract`, texture ops (`hue`, `tint`, `levels`, `overlay`, `replace`, masks, `sheet`),
  material parameters (`mat list/set/reset`), `build`, `validate` (9 rules, evidence tiers), deterministic
  `package`, receipt-based `deploy`/`undeploy`, `check-load` with log signatures and owner confirmation.
- `doctor`, `plan` (request router), `capabilities`, `guide`, `knowledge`, `facts`, `selftest texture`.
- Installer (`Install.ps1`, `Uninstall.ps1`, `START-HERE.bat`), agent skill, offline test suite with tool shims, CI.
