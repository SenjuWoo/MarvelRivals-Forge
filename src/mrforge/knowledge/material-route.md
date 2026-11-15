# Material route (tints, glow, roughness, rim colour)

Material instances (`MI_*`) override parameters of a parent material. The forge edits those overrides through
UAssetTool's JSON (to_json / from_json). Verified: all parameters survive the round trip and an edited value reads
back from the packed mod (validate rule V-MAT).

```
mrforge new "Glow Up" --skin 1061303 --kind material
cd projects/glow-up
mrforge extract --materials
mrforge mat list MI_1061303_Body_01
mrforge mat set MI_1061303_Body_01 BaseTint "#ff3366"          # vector: #rrggbb or r,g,b[,a] (HDR > 1 allowed)
mrforge mat set Lobby/MI_1061303_Body_01 Roughness 0.8         # scalar
mrforge build && mrforge validate
```

- A bare name (`MI_x`) edits the in-match and Lobby copies; prefix `Lobby/` or `Materials/` to target one.
- Only parameters the instance already overrides can be set. Parameters that exist only on the parent cannot be
  added in v0.1 (`mat list` is the source of truth).
- Texture parameters (which texture a slot uses) cannot be changed in v0.1: edit the texture itself.
- Zero-valued colours are stored without a value (unversioned `IsZero`). Setting one adds the value and drops the
  captured unversioned header; keeping the header corrupts the asset (tested).
