# Tools (pinned in tools.lock.json)

| Tool | Role | Notes |
|---|---|---|
| retoc-rivals-cli v3.11.1 | packer, `info`, `manifest --filters` | output name = input folder + `_9999999_P` |
| UAssetTool v1.5.9 | vanilla extraction, texture extract/inject, JSON, mesh info, listing | first extraction fetches `oo2core_9_win64.dll` itself |
| fmodel-mcp v1.2.0 | mesh export (stdio MCP) | v0.2 mesh route |
| ueformat-blender v10 | headless .uemodel import in Blender | v0.2 mesh route; never installed into Blender |

- `mrforge setup` resolves each tool: installed copy with the pinned exe hash -> a copy under `--from <dir>` with
  that hash -> the GitHub release asset (asset hash checked, then exe hash). No installer ever runs.
- Tool behaviour worth knowing:
  - UAssetTool `--filter` is a substring match (`SK_1061_1061303` also matches `_Lobby` and `_Lobby_Physics`).
  - UAssetTool `extract_texture` needs absolute output paths.
  - `extract_iostore_legacy` without `--mod` reads only vanilla containers; with `--mod <utoc>` it reads the mod.
  - `list_iostore <Paks> --filter Characters/` lists ~314k packages in ~5 s.
- Updating after a game patch: check the upstream releases, update tag and both hashes in `tools.lock.json`,
  run `mrforge setup --force`, then `mrforge selftest texture`.
