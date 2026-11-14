# 15 — Phone build on the Remake base

Date: 2026-11-14. Card: gcg2#34. State: installed on the Galaxy S24+: our repacked APK (English intro) and release `gcg2-0.1.3-8`.

Since 2026-11-14 the project base is [GirlCafeGun-Remake](https://github.com/zirenmidori/GirlCafeGun-Remake).
This page says how the phone gets "Remake plus our changes" and what was proved at each step.
Docs 01 to 14 describe the older C# build and do not apply to this route.

## The route

Two layers:

1. **The APK**: the published Remake 0.1.3 APK with one entry changed (`assets/bin/Data/data.unity3d`: three intro
   pictures) and **our signature** (`CN=GCG2-Offline community update, O=iHealthSi`, cert sha256 `b2ef7cc0...`).
   The owner chose this on 2026-11-14 to get an English intro. Until then the phone ran the publisher's APK unchanged.
2. **Our signed update packages** (`.gcgupdate`) for everything in the game data, the way Remake's
   `docs/update-format.md` describes under "Locally signed user-created data updates". The app shows the
   fingerprint of our key (`dbce3bad83600b1a7540b07d4eb734ac6065ee2e90b589ef3cffcdce8ee6dac3`) and asks to trust it
   once per package.

A full rebuild from source is not possible: Remake's build pins a client APK and a signing key that we do not have.

What the repacked APK costs: the publisher's APK updates do not install over it (another signer). A new official
APK must go through `tools\remake\repack_apk.py` first. Our own APK changes install with `adb install -r`.

What is installed as data (release `gcg2-0.1.3-8`, one package on a fresh `0.1.3`; releases 1 to 7 were the
steps on the publisher's APK, 2 to 6 of them diagnosis):

| Part | From | Content |
|---|---|---|
| `lua.u` | Remake pull requests 2 and 4, plus one hook of this tool | controller layer in `UI_Fight.lua`; four title screens in `UI_Login.lua`; the age badge and the health notice of the Chinese release are off |
| `ui_tx/ui_login.u` | our English client data | the English logo, "Tap Screen to Start" and "Log Out", painted into Remake's own login atlas |
| `version.data` | derived | size and CRC of the changed bundles; every other record byte for byte |
| server payload | Remake pull request 1 | daily save backup, broken-save protection |

Not on the phone: pull request 3 (the story editor is a PC tool) and the InputManager axes of the controller
work (they need an APK change). Without them the right stick and the d-pad depend on the pad; see Remake
`docs/controller.md`.

## Why the title was Chinese, and what cannot be changed

Remake's client is the **Chinese package** (versionName 1.1.36). `Game.Localization.Lang` is `zh_CN` and the text
table is translated, so text is English but art with text in it is the Chinese art.

- Title logo, "tap to start", "log out": sprites of the atlas `UI_Login` in `ui_tx/ui_login.u`. Remake's data and
  our English data (build 179) hold the same bundle: 27 sprites, the same keys, other pixels. Fixed by the `art` stage.
- Age badge (`BtnAgeLimit`) and health notice with the licence line (`TipCN`): `UI_Login.lua` shows them when the
  language is `zh_CN`. Fixed by the `--english-title` hook.
- **Intro** (publisher splash, Seasun logo, the Chinese health notice screen): three textures inside
  `assets/bin/Data/data.unity3d` **of the APK**. A data update cannot reach them. Fixed by the repacked APK:

  | Texture | Was | Is |
  |---|---|---|
  | `bg_start_Mul` | "bilibili 游戏" | the "bilibili" picture of the English client APK (`gcg_offline_fixed.apk`) |
  | `bg_start2_Mul` | Seasun logo with 西山居 under it | the same picture without the characters |
  | `bg_LaunchTip_JP` | health notice of the Chinese release | black, the English game logo in the middle |

  Each is ETC_RGB4, 2048 x 1024, one mip, 1,048,576 bytes in a `.resS` stream: the new pixels go over the old
  bytes in place, and the tool asserts that no other byte of the unpacked file changed.
- Other art with text in it (`*_Mul` sprites in other screens) was not looked at.

## Inputs

| Input | Where | Identity |
|---|---|---|
| Remake release APK 0.1.3 | `Other version\GCG-Offline-v0.1.3.apk` | sha256 `35c8b53916df27e8d7dd1dbef05cd5ccb37b727fd04d6f25523a1efbefa9bffa`, 405,366,349 bytes, signer `CN=GCG Offline Release, O=zirenmidori` (cert sha256 `b831f434...`), versionCode 10141, target SDK 29 |
| Merged source | Remake clone, local branch `gcg2-phone-build` (worktree `repos/GirlCafeGun-Remake-wt-phone`): `origin/main` `4fbad28` + the four pull request branches. Never pushed. | head `37e5a5b` |
| English login atlas | `assets\Bundles\ui_tx\ui_login.u` (EN build 179) | sha256 `aa753d9e...` |
| Files of the installed release | pulled from the phone: `version.data`, `ui_tx/ui_login.u` | `dist\remake-phone\` |
| Python 3.10 venv | `release/client/requirements.txt` (UnityPy 1.25.2, lupa) | |
| Node.js 22+, JDK 21 | `server/node_modules` of the Remake clone; `C:\android-build\jdk` | |
| Our signing identity | `.local\remake-signing\` (key, password, `publisher.der`) | local only, never commit |

The controller and title pull requests conflict in three files (`docs/upstream.md`, `release/client/build.py`,
`release/client/patch_lua.py`): both add a line at the same place. The build branch keeps both sides.

## Steps

All commands run from the repo root. `PY310` is the venv Python, `APK` the release APK, `WT` the worktree,
`FILES` = `/sdcard/Android/data/com.zirenmidori.gcg.offline/files`. In Git Bash set `MSYS_NO_PATHCONV=1` for adb.

```powershell
# 0a. the APK with the English intro, signed with our key (only when the APK must change)
PY310 tools\remake\repack_apk.py intro --apk APK --en-apk gcg_offline_fixed.apk --en-atlas assets\Bundles\ui_tx\ui_login.u --remake WT --out dist\remake-phone\apk\data.unity3d
python tools\remake\repack_apk.py apk --apk APK --data dist\remake-phone\apk\data.unity3d --signing-dir .local\remake-signing --build-tools C:\android-build\bt\android-15 --java-home C:\android-build\jdk\<jdk> --out dist\remake-phone\apk\GCG-Offline-v0.1.3-gcg2.apk
# 0b. the phone: install it (the owner accepts the Play Protect prompt). Over our own APK: adb install -r.
C:\platform-tools\adb.exe install dist\remake-phone\apk\GCG-Offline-v0.1.3-gcg2.apk

# 1. lua.u: the released script bundle plus our recipes, then the mock tests on the result
PY310 tools\remake\build_phone_update.py lua --apk APK --client-dir WT\release\client --hooks-only --english-title --tests --out dist\remake-phone\lua.u

# 2. login atlas with the English sprites
C:\platform-tools\adb.exe pull FILES/ui_tx/ui_login.u dist\remake-phone\from-phone\ui_tx\ui_login.u
PY310 tools\remake\build_phone_update.py art --remake-atlas dist\remake-phone\from-phone\ui_tx\ui_login.u --en-atlas assets\Bundles\ui_tx\ui_login.u --out dist\remake-phone\extra\ui_tx\ui_login.u

# 3. server payload. Drive D: has no junctions, so the source goes to a folder on C: first:
git -C WT archive gcg2-phone-build server/src server/tsconfig.json server/tsconfig.build.json server/package.json | tar -x -C <C:\scratch>
python tools\remake\build_phone_update.py server --apk APK --server-dir <C:\scratch>\server --node-modules repos\GirlCafeGun-Remake\server\node_modules --remake WT --work <C:\scratch>\srv --out dist\remake-phone\payload.zip

# 4. sign and pack on top of the release that is installed now
C:\platform-tools\adb.exe pull FILES/version.data dist\remake-phone\version.data.now
PY310 tools\remake\build_phone_update.py pack --apk APK --remake WT --lua dist\remake-phone\lua.u --extra dist\remake-phone\extra --payload dist\remake-phone\payload.zip --version-data dist\remake-phone\version.data.now --release-id <new id> --signing-dir .local\remake-signing --java C:\android-build\jdk\<jdk>\bin\java.exe --work dist\remake-phone\pack-work --out dist\remake-phone\<new id>.gcgupdate
#    when the installed release is one of ours, add: --base-manifest dist\remake-phone\manifest-<installed id>.json
#    pass --extra and --payload only when those parts changed

# 5. to the phone and apply (the game shows its title screen)
C:\platform-tools\adb.exe push dist\remake-phone\<new id>.gcgupdate FILES/updates/
python tools\remake\apply_update_on_phone.py --package-name <new id>.gcgupdate --fingerprint dbce3bad83600b1a7540b07d4eb734ac6065ee2e90b589ef3cffcdce8ee6dac3
```

Rules of the update chain:
- A package applies only on the release it names as its base. The installed id is now `gcg2-0.1.3-8`; the next
  package needs `--base-manifest dist\remake-phone\manifest-gcg2-0.1.3-8.json`. `dist\` is not in git: keep that file.
- The game rewrites `files/version.data` at its first start after an install or update (the asset routes
  change, the bundle records do not). So always build on the copy pulled from the phone, not on the copy of the
  release manifest. The pack stage checks that the copy describes the installed release.

## What was proved on the PC

- **Server parity.** `origin/main` (`4fbad28`) compiled with the same `tsc` flags as Remake's
  `build-server-payload.py` gives exactly the 65 modules of the 0.1.3 payload (0 differ). So a payload built
  here differs from the release only by our source changes.
- **Server payload.** 707 entries; 642 kept byte for byte from the release (bootstrap, config, tables, zod); 6
  modules differ, all touched by pull request 1: `config.js`, `index.js`, `persistence/json-store.js`,
  `persistence/player-repository.js`, `game-data/bounty-data.js`, `game-data/phone-message-data.js`.
  sha256 `ee7705de439d93220740e413c2bde1e4d2691c4c7f5d66a34fe92e38af14d349`, 1,274,550 bytes.
- **Payload smoke test** (Node 24 on Windows, `bootstrap.mjs` with a fresh state path): the server starts and
  answers on 127.0.0.1:28080; the second start writes `data/backups/state-20261114.json`; with a broken
  `state.json` the server stops, keeps `state.json.corrupt-<time>` and names the latest backup.
- **lua.u.** Source: `assets/lua.u` of the release (sha256 `4dd630bd...`). Installed result: sha256
  `04571a8aafb8dfd9233223340616a8f178b40b7230d1f2ee82f3e64c2ed34677`. Changed scripts: `UI_Fight.lua`,
  `UI_Login.lua`. Every other object of the bundle is byte for byte the same (the checks in `patch_lua.build`).
  `test_gamepad.run_bundle` and `test_title.run_bundle` pass on the built bundle. A second run of the tool gives
  the same hash.
- **Login atlas.** Three rectangles painted (logo 695 x 292, tap text 210 x 41, log out 100 x 100); the tool
  asserts that no pixel outside them changed and that the bundle reads back with the same 27 sprites and
  rectangles. The texture is stored as RGBA32. sha256 `09e87e83...`, 382,391 bytes.
- **Not possible:** a full run of Remake's `patch_lua.py` on `assets/lua.u.orig` of the release APK. That file is
  not the input their build pins: `patch_selectors` stops on its first anchor. So the release cannot be
  reproduced from the APK alone, and the hooks-only way is the one we use.

## Moving from the publisher's APK to ours (done once, 2026-11-14)

Another signer means an uninstall, and an uninstall deletes the save and `Android/data/<package>`. What worked:

1. Put the changed bundles back to their 0.1.3 originals in `files/` (`lua.u`, `ui_tx/ui_login.u`), so that the
   new install finds the data of its own manifest.
2. `adb shell mv <package dir>/files /sdcard/Android/data/gcg-remake-keep` (a rename: instant).
3. `adb uninstall`, `adb install` (Play Protect prompt), start the app once, stop it.
4. `adb shell rm -rf <package dir>/files`, then `mv` the kept folder back. This time `mv` copied (about a minute for
   5.9 GB): the new install has another user id. The copies belong to `shell`; the app reads and writes them.
   The Unity cache folders `Unity/` and `il2cpp/` of the old install could not be removed by `shell`: 18 MB stay
   in `/sdcard/Android/data/gcg-remake-keep` on the phone.
5. Start the app: "Verifying and committing game data… 100%" with no download, then the game.
6. Apply one full package on base `0.1.3` (`gcg2-0.1.3-8`: `lua.u`, `ui_tx/ui_login.u`, `version.data`, server).

The save started new (the owner asked for a fresh save).

## What was seen on the phone (Galaxy S24+, 2026-11-14)

- On our APK: the intro shows "bilibili", then the Seasun logo without characters, then the game logo. Eight
  starts of release `gcg2-0.1.3-8` logged snow 4, shards 2, sky 1, hall 1, all with the English logo.

- The app accepts our packages: fingerprint prompt, "Update completed", the game starts. The hashes of
  `lua.u` and `ui_tx/ui_login.u` in `files/` equal the built files. Files in `files/` win over the copies inside
  the APK.
- Title: English logo, "Tap Screen to Start", no age badge, no notice.
- **Title rotation.** With the first version of the title module only `hall` and `sky` came up. Log:
  `snow left out: no animation suit 1`, `shards left out: no animation suit 3`. Cause: `ShowConcertModel:Load()`
  of this client does nothing while a model stands (after `Load()` the component still held
  `girl1002_2da02(Clone)`, also one second later). Fix in the module (Remake branch `gcg2-title-screens`,
  commits `9e9a8ab`, `6d91c7b`, local, not pushed): take the old model away and call `Load()` once more. Result
  with the fix: `hall`, `snow`, `shards`, `sky` all came up and were looked at; the last ten starts of the final
  build logged sky 2, hall 4, snow 4 and no "left out" line.
- **Log.** `Login.lua` sets `U3D.Debug.unityLogger.filterLogType = 4` before the login screen, so `print` from Lua
  is silent from there on. The title module lifts the filter for its own lines:
  `adb logcat -s Unity | grep "\[title\]"`.
- Not checked on the phone: the controller layer in a fight, the save backup files (app-private, not readable
  by adb), play after login.

## After an official Remake update

Our release id is installed, so the publisher's delta (base `0.1.3`) does not apply as it is. To move to a new
official release:

1. Get the new official APK, repack it (`repack_apk.py intro` and `apk`; check the three textures are still
   there) and install it over ours with `adb install -r` (same signer: ours; the save stays).
2. Rebuild the steps against the new APK and its manifest, with a new release id (`gcg2-<release>-1`).
   If upstream merged one of our pull requests, drop that part.
3. Open question: whether the app accepts a full official data set over our release id without a reinstall.
   Check it before the first real update; the save is at risk only on an uninstall.

The weekly scheduled task `gcg2-weekly-upstream-check` reports when this is needed.
