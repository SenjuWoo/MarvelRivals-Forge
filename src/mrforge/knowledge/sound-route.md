# Sound route (v1.2): your own audio in a skin's sounds

No Wwise and no Unreal Editor. Verified at the package tier on build 4066382 (skin 1061303); heard in game only
after `mrforge check-load --confirm`.

```
mrforge new "Loud Claws" --skin 1061303 --kind sound
cd projects/loud-claws
mrforge extract --sounds                  # bnk_sfx_<skin>.bnk + bnk_display_<skin>.bnk, with their events
mrforge sound list "*left*"               # events, variations, layers
mrforge sound replace sfx_1061303_left_release1_play claw.mp3 --gain -3
mrforge build && mrforge validate && mrforge package
```

Where the sounds are
- Wwise sound banks and streamed media are loose files in the legacy pak `pakchunkWwise-Windows.pak` (mount
  `Marvel/Content/WwiseAudio/`); newer copies sit in the `Patch_*` pak, which wins. Each skin has its own
  `bnk_sfx_<skin>.bnk` (weapon and ability sounds) and `bnk_display_<skin>.bnk` (hero select, MVP). Hero voice
  lines are in `<language>/bnk_vo_<hero>001.bnk`, shared by every skin of the hero (`--bank`, with a warning).
- Event names come from the WwiseEvents packages: `left_release1..3` = primary fire combo, `right_*` = secondary,
  `e/q/shift/f_*` = abilities, `display_*_hover_to_full` = the hero-select hover sound. A Wwise event id is the
  FNV-1 hash of its lower-case name; events whose name is not a package are listed by id.

How replace works
1. The input is converted with ffmpeg to 48 kHz 16-bit stereo (a 16-bit WAV is taken as it is) and cut at 30 s.
2. An event usually plays a random container (variations) plus one or two layers at once. Every variation gets
   the new sound; the layers get 10 ms of silence so the sound plays once (`--keep-layers` keeps them).
   `replace` warns when a changed media id is also played by other events.
3. `build` writes the sound as a Wwise PCM .wem in place of each vanilla media in the bank's DIDX/DATA. The HIRC
   (events, containers, Sound objects) stays byte-identical: pointing a Sound object at a new media id crashed the
   game in another tool. The game plays PCM media under the bank's Vorbis entries; this is the route community
   sound mods ship. A streamed sound also gets the file at `Media/<first two digits>/<id>.wem`.
4. The banks go into the mod's companion pak at `Marvel/Content/WwiseAudio/` (one container with any other route;
   a sound-only mod is a single `.pak`). `build` and V-SND read them back out of the built pak: game HIRC and
   untouched media kept byte for byte, replaced media equal the new sound.

Limits
- Since the game's September 2026 update it loads one copy of each bank: two mods carrying the same bank conflict
  (V-CONFLICT names them); the higher pak order wins.
- No preview of the game's own sounds (ffmpeg cannot decode Wwise Vorbis); the event names say what each is.
- A game patch that changes a bank changes its vanilla hash; rerun `mrforge extract --sounds` and `build`.
