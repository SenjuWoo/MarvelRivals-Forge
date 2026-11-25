# Asset layout (game build 1.1.4042190, Season 11.0)

- Vanilla content: `MarvelGame/Marvel/Content/Paks/*.utoc|ucas|pak|sig`, 39 IoStore containers, ~590k packages.
- Mods: `Paks/~mods/**` (subfolders allowed). A mod is `<Name>_9999999_P.{pak,utoc,ucas}`, mount point `../../../`.
- A skin id has 7 digits; the first 4 are the hero id. Skin folder:

```
Marvel/Content/Marvel/Characters/<hero>/<skin>/
  Meshes/SK_<hero>_<skin>.uasset            in-match mesh
  Meshes/SK_<hero>_<skin>_Lobby.uasset      lobby / hero-select mesh
  Materials/MI_<skin>_<Part>.uasset         in-match material instances
  Materials/Lobby/MI_<skin>_<Part>.uasset   lobby copies (same names)
  Textures/T_<skin>_<Part>_{D,N,ORM,S,M}.uasset
  Post_<skin>_Physics.uasset, Post_<skin>_Lobby_Physics.uasset
Marvel/Content/Marvel/VFX/{Meshes,Textures}/Characters/<hero>/<skin>/   skin VFX
```

- Folder names are not uniform: in build 4066382, 240 of 751 skin folders keep their textures in `Texture/`
  (singular, e.g. Storm 1015001) and 24 keep materials in `Material/`. `mrforge extract` accepts both spellings.

- Materials often point at parents and textures of the hero's default skin (`<hero>001`), e.g.
  `MI_1061303_Body_01` has parent `M_1061001_Skin`. Editing such a shared asset changes every skin that uses it.
  `mrforge skin inspect <id>` lists these under `shared_from_other_skins`.
- Lobby and in-match use separate material instances: a recolor usually needs both. `mrforge mat set` with a bare
  name edits both copies.
- `mrforge index` stores every vanilla package path for the installed build; `validate` (V-PATHS) checks that a mod
  only replaces paths that exist in that build.
