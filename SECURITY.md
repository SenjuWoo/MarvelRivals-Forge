# Security

## What the forge touches

- Writes: this checkout, `.mrforge/` (tools, caches, keys, receipts, logs), `projects/`, and with `mrforge deploy`
  only `<game>/MarvelGame/Marvel/Content/Paks/~mods/<prefix>-mrforge-<id>/`.
- Reads: the game install, installed mods (to report flags and conflicts), Steam library files.
- Network: GitHub release assets for the pinned tools, the mapping/key depot, and (on request) the skin name table.

## Supply chain

- Tools are pinned by tag, release-asset SHA-256 and executable SHA-256 in `tools.lock.json`. A mismatch stops
  setup. Archives are checked for path traversal before extraction. No installer is ever run.
- Subprocesses are started from argument lists, never through a shell.
- The AES key is stored in `.mrforge/keys.json` (git-ignored) and is redacted from all output and logs.

## Game policy

The forge builds plain IoStore containers only. Since Season 11 the game's anti-cheat reports encrypted, obfuscated
and stripped mods; `mrforge validate` fails on an encrypted container and `mrforge doctor` lists installed mods with
those properties.

## Reporting

Open a GitHub issue. Do not include game files, keys or personal paths in reports.
