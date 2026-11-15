# Packaging and deploy

- `mrforge build` stages only changed packages under `build/stage/<PakName>/Marvel/Content/...` and runs
  `retoc-rivals-cli pack <stage> --output dist` -> `dist/<PakName>_9999999_P.{pak,utoc,ucas}` (Oodle,
  flags `Compressed | Indexed`). `dist/receipt.json` records inputs, tool versions and hashes, build and usmap.
- Never `--obfuscate`, `--strip` or encryption: since Season 11 the game reports such mods.
- `mrforge validate` rules: V-NAME, V-FLAGS, V-PATHS, V-LEAK, V-STALE, V-RECEIPT, V-TEX, V-MAT, V-CONFLICT.
  Tiers: static / build / package are proven by the forge; load / gameplay only by looking in game.
- `mrforge package` -> `dist/<PakName>-<version>.zip` (the triple in a `<PakName>/` folder, plus README.txt when the
  manifest has a description). Deterministic: the same build gives identical bytes. Import it with a mod manager.
- `mrforge deploy` copies the triple to `~mods/ZZZ-mrforge-<id>/` (sorts after mod-manager folders) and writes a
  receipt in `.mrforge/receipts/`. `mrforge undeploy` removes only receipt-listed files whose hash still matches.
  Both refuse while the game runs. No other folder in `~mods` is touched.
- Version bumps: `mrforge bump [major|minor|patch] --note "..."` updates `mrforge.json` and `CHANGELOG.md`.
