# Texture route (recolor, decal, logo, skin tone, repaint)

Editor-free and proven end to end: vanilla texture -> PNG -> edit -> inject (pixel format and mip chain kept)
-> pack -> validate by extracting the texture back out of the built mod.

```
mrforge new "Red Suit" --skin 1061303 --kind texture
cd projects/red-suit
mrforge extract --textures "T_1061303_Body_*"
mrforge tex list
mrforge tex hue  T_1061303_Body_01_D --shift 120
mrforge tex tint "T_1061303_Equip_*_D" --color "#c01020" --strength 0.7 --mask mask.png
mrforge tex levels T_1061303_Body_01_D --black 10 --white 235 --gamma 0.9
mrforge tex overlay T_1061303_Body_01_D logo.png --at 512,300
mrforge tex replace T_1061303_Body_01_D my_paint.png
mrforge tex sheet          # open build/preview/sheet.png and look at it
mrforge build && mrforge validate && mrforge package
```

Rules
- Ops are recorded in `work/ops.json` and replayed from the vanilla PNG on every build, so they never stack.
- `_D` = colour. `_N` = normal map: colour ops are refused (they break lighting). `_ORM`, `_S`, `_M` are channel
  packed (occlusion/roughness/metallic, masks): colour ops warn because they mix channels.
- Masks are grayscale PNGs (white = apply, black = keep vanilla), resized to the texture.
- Hand painting: paint a copy and capture it with `tex replace`. Painting `work/textures/*.png` directly after ops
  stops the build with HAND_EDIT_CONFLICT instead of silently losing the paint.
- `tex replace` resizes to the vanilla size unless `--keep-size` (other sizes are unverified in game).
- Block compression (DXT1/BC5/...) loses a little: round trip RMSE about 0.3% on a 2048 DXT1 body texture.
- A texture under another skin id (e.g. `<hero>001`) changes every skin that uses it; build warns.
