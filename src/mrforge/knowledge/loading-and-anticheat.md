# Loading and anti-cheat

- The game loads `~mods` only with the ASI loader (`Binaries/Win64/dsound.dll`) and the UTOC signature bypass
  plugin (`plugins/*.asi`). `mrforge doctor` and `mrforge game` report both; the forge never installs them.
- Since Season 11 the anti-cheat reports encrypted, obfuscated and stripped mods (retoc-rivals-cli 3.11.1
  changelog). The forge only writes plain containers, and `doctor` lists installed mods with those flags.
- Load order: among mods replacing the same package the later-sorted folder is assumed to win (unverified). The
  forge deploys to `ZZZ-mrforge-<id>` so it sorts last; `validate` warns (V-CONFLICT) with the other mod's name.
- After a game patch the changelist changes: run `mrforge sync` and `mrforge index`, then rebuild; V-STALE fails
  for mods built for an older build.
- Proof of loading: deploy, open the hero in the lobby with the skin equipped, then
  `mrforge check-load --confirm "<what you saw>"` (records the load tier in the project).
  `check-load` also scans the newest game log and Galacta.log for known failure signatures.
