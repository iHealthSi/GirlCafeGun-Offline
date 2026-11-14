# 12 - Late content (chapters 13-16, banners after July 2022)

Date: 2026-11-14. Card: gcg2#29. State: the late set is built, checked on the PC, and starts on the phone up to the
title screen. Play after login is not checked yet.

GirlCafeGun-Remake, the project base since 2026-11-14, already has chapters 1-16 and 82 pools; this set matters only for the C# build.

The save is copied once per day, before the server starts, to `Android/data/<pkg>/files/save-backup/<YYYYMMDD>/`
(gcg2#31). Pull it with `adb pull` before a risky change.

## Two content sets
| | `build5` (parked) | `late` (active now) |
|---|---|---|
| Source | OBB as shipped (EN v1.0.9, build 5) | last EN hot update (build 179), the files in `assets/Bundles/` |
| Main story | chapters 1-12 | chapters 1-16 |
| Character banner pools | 25 (newest: July 2022) | 42 (newest: March 2023) |
| Weapon banner pools | 8 | 12 |
| Table files the extractor writes | 1,168 | 1,285 |
| Other effects | | player level cap 150 -> 300, card level caps 60/80 -> 100/100 (server startup log), 4 new items |
| English text | 16,186 values in Chinese, translated by us | official English for 13,495 of them; 2,691 of ours kept; 22 new keys |

Sources: `tools/extract_setting.py <obb|late> x --compare server/setting`, the server startup log on each set,
`tools/tableset.py build-late` output.

Build 179 changes little in the client: 16 of 830 Lua scripts and 2 new ones, 22 language keys, and 100 other
bundles that the OBB holds in an older form (`assets/device_assets/late_changed_bundles.txt`, 463 MB).
The server already has the build-179 calls (for example `ChapterStoryFeature`, LuaCall 540, used by chapter 16).

## Commands
```
python -I tools/tableset.py status
python -I tools/tableset.py build-late [--force]
python -I tools/tableset.py use late
python -I tools/tableset.py use build5
```
- `build-late` makes the parked late set. It changes nothing that is active.
- `use <set>` swaps the sets by renaming folders. The active set is always in `server/setting/`,
  `assets/device_assets/overrides/` and `assets/device_assets/version.data`. The other set is parked in
  `server/setting.<name>/` and `assets/device_assets/sets/<name>/`. `assets/device_assets/tableset.txt` names the active set.
- After `use`: build the APK again (the server tables are inside it) and sync the phone or build the data pack.
  `assets/sync_phone.ps1` and `apk-build/make_data_package.py` read `tableset.txt`. For `late` they also send the 100
  changed bundles.

## What `build-late` makes
1. **Server tables** from `assets/Bundles/setting.u` (`tools/extract_setting.py`). The extractor makes the current
   `server/setting` from the OBB byte for byte (1,168 files), so the layout rules are correct. `ItemList.txt` comes from
   the ItemList object in the same bundle. `CharacterCard.txt`, `Rune.txt`, `Weapon.txt` and `CartoonFileId.txt` are
   copied: their source objects have the same size in the two builds.
2. **`gacha-rotation.json`**: all 54 pools open from 2020 to 2030, each with its newest period. Pool 43 changed its
   featured cards every 15 days (31 periods); the file runs these periods one after the other, 15 days each, from 2026-11-01.
3. **`lua.u`**: the build-179 scripts plus our patches. 33 patched scripts are unchanged in build 179 and are copied.
   `UI_Gacha.lua` and `UI_User.lua` are merged with `git merge-file` (no conflict). The tool stops if a merge has a conflict.
4. **`lang.u`**: the build-179 table. Our translation is kept only where build 179 still has the build-5 text.
5. **`setting.u`**: the build-179 file, not changed. `versioncrc.json` holds the CRC32 of `lua.u` and `setting.u`
   (the game decrypts these two bundles only when the CRC matches).
6. **`version.data`**: the build-179 bundle table from `assets/Bundles/` (the build5 set uses a merged build-5 table).

## Checks done on the PC
- Server: `dotnet build` OK. Start on `server/setting.late` (at the time of the check; the set is now `server/setting`): `Chapter.txt` 531 levels (build5: 387), 42 character pools
  and 12 weapon pools open, no new warning except "duplicate ID" notes for 4 pool files of pool 43.
- `lua.u`: 832 scripts; no patched line is lost; the bundle reads back; CRC matches `versioncrc.json`.
- `lang.u`: reads back with the same keys and values that were written.
- `use late` and `use build5`: both directions work; after each one the extractor finds no difference.

## Phone test, 2026-11-14 (Galaxy S24+, scratch APK from the late set, `assets\sync_phone.ps1`)
- The game starts and reaches the title screen. From `adb logcat`: `local version file size:2084731`,
  `set localVersion. buildVersion=179`, `load bundle lua.u`, `load bundle setting.u`, the recomputed CRC values equal
  `versioncrc.json`, `DownloadVersionList buildversion is 0. dont update`, `UI_Login`, `Server List Get success`.
- So the build-179 `version.data` in `files/` is accepted.
- Log errors at start: `AchievementOther Repeated Error` (39 ids, table data) and
  `failed to load asset: .../WishingTreeActivity.txt` (the table is in neither build). No Lua error.
- Not checked yet: login with the old save, the banner screen, a chapter 13-16 stage.

## Still open
- Stories of chapters 13-16: the scripts are in `com.u` (18, 24, 25 and 24 scripts). Voice for them was not checked.
- New Chinese text in build-179 scripts: 3 lines (`AutoTest.lua`, `LuaCall.lua`), not player text `[INFER]`.
- Old saves: a save made on `build5` was not loaded on `late`.

## Go back
`python -I tools/tableset.py use build5`, build and install the APK again. On the phone, delete `setting.u` and the files
named in `late_changed_bundles.txt` from `Android/data/<pkg>/files/`, then run `assets/sync_phone.ps1` (it does not delete files).
