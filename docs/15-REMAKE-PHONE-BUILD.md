# 15 — Phone build on the Remake base

Date: 2026-11-14. Card: gcg2#34. State: installed on the Galaxy S24+: our repacked APK (English intro, controller axes) and release `gcg2-0.1.3-20` (2026-11-15: release 10 = local Notice and server-error pages, event page rewards; 11 and 12 = a save-reset step in the server, added and removed again; 13 to 15 = menu navigation with the pad; 16 = the same, built from `origin/main` after pull requests 1 to 6 merged, pad overlay images start hidden; 17 to 20 = Irene lifted on the snow title). The APK is debuggable for the save tool. Remake pull request 5 holds those two ports.

Since 2026-11-14 the project base is [GirlCafeGun-Remake](https://github.com/zirenmidori/GirlCafeGun-Remake).
This page says how the phone gets "Remake plus our changes" and what was proved at each step.
Docs 01 to 14 describe the older C# build and do not apply to this route.

## The route

Two layers:

1. **The APK**: the published Remake 0.1.3 APK with one entry changed (`assets/bin/Data/data.unity3d`: three intro
   pictures and 28 raw joystick axes in the InputManager) and **our signature** (`CN=GCG2-Offline community update, O=iHealthSi`, cert sha256 `b2ef7cc0...`).
   The owner chose this on 2026-11-14 to get an English intro. Until then the phone ran the publisher's APK unchanged.
2. **Our signed update packages** (`.gcgupdate`) for everything in the game data, the way Remake's
   `docs/update-format.md` describes under "Locally signed user-created data updates". The app shows the
   fingerprint of our key (`dbce3bad83600b1a7540b07d4eb734ac6065ee2e90b589ef3cffcdce8ee6dac3`) and asks to trust it
   once per package.

A full rebuild from source is not possible: Remake's build pins a client APK and a signing key that we do not have.

What the repacked APK costs: the publisher's APK updates do not install over it (another signer). A new official
APK must go through `tools\remake\repack_apk.py` first. Our own APK changes install with `adb install -r`.

What is installed as data (release `gcg2-0.1.3-8`, one package on a fresh `0.1.3`, plus release 9, which adds
the recovered bundles; releases 1 to 7 were the steps on the publisher's APK, 2 to 6 of them diagnosis):

| Part | From | Content |
|---|---|---|
| `lua.u` | Remake pull requests 2 and 4, plus one hook of this tool | controller layer in `UI_Fight.lua`; four title screens in `UI_Login.lua`; the age badge and the health notice of the Chinese release are off |
| `ui_tx/ui_login.u` | our English client data | the English logo, "Tap Screen to Start" and "Log Out", painted into Remake's own login atlas |
| `version.data` | derived | size and CRC of the changed bundles; every other record byte for byte |
| server payload | Remake pull request 1 | daily save backup, broken-save protection |

Not on the phone: pull request 3 (the story editor is a PC tool).

## What came over from the C# build, and what did not (2026-11-14)

| Fix of the C# build | On the Remake phone build |
|---|---|
| Controller layer | in (pull request 2). The raw axes `gcgpad_a1..28` are in our APK since the second repack; not tried with a pad. Menu navigation (2026-11-15, new, not in the C# build): built as `lua-r13.u`, not packed yet |
| Four title screens, English title art, English intro | in |
| Daily save backup | in (pull request 1) |
| Story translations | not ours, and not needed: Remake's text table has no value with a Chinese or Japanese word; chapter 16 is the official text |
| Uncensor switch (`love.u`) | not needed: Remake's server sends Live2D level 3 and the censor flag off at login (`server/docs/modules/16-live2d-state.md`), as our C# server does. The `love.u` marker only acts when the client language is English, which it is not here. Not checked in play |
| 16 bundles recovered from EN 1.0.7 | in release `gcg2-0.1.3-9`: the two theme songs (Remake's index names them with exactly our size and CRC, its data lacks the files) and the 13 `update/` bundles (its index does not name them: effect on this client unknown; one package with `--remove` takes them out). `charact/player.u` exists there in its own version |
| The 427 bundles our data lacks | Remake's data lacks the same ones; it ships voice as loose `AutoAudio` files. Story voice was not listened for |
| Free store packs offline | left out on the owner's decision (Remake grants only the daily gift and one month card) |
| GM panel fixes | left out on the owner's decision (Remake removes the GM panel) |
| Stamina recovery over time | left out on the owner's decision; ported and parked on the Remake branch `vigour-recovery-parked` |
| Local Notice and server-error pages | ported on the Remake branch `gcg2-offline-web` (card gcg2#35, pull request 5); in release `gcg2-0.1.3-10`, applied 2026-11-15. Notice loads `/notice.html` of the local server; Help and Glossary load a page that says there is no local copy; the server-error window shows its text from inside the script. Not seen on the phone. The client's own notice reader still asks a publisher host at each start |
| Event page rewards | ported on the Remake branch `gcg2-activity-rewards` (card gcg2#36, pull request 5); in release `gcg2-0.1.3-10`, applied 2026-11-15. Reward items that the game uses up on receipt (coins, head frames, cards, skins, chat bubbles, gallery entries) are paid by their `ItemList` rule in every reward path. This client shows 12 event pages. Claims work for pages 2, 3, 15 and 108, only for the achievements whose progress comes from the saved state; pages 1 and 29 as before. Not handled: 8 (timed stamina), 14 (no progress source), 16 (refused: its reward item has no rule), 20 line rewards, 83, 149. Not checked in the game |
| Gacha fixes | not needed: Remake's design prevents those bugs |

Published on 2026-11-14: Remake fork `iHealthSi/GirlCafeGun-Remake`: the four pull request branches and the combined
branch `gcg2-phone-build` (what the phone build is made from). C# fork `iHealthSi/GirlCafeGun-Offline`: branch
`gcg2-all-fixes`, one commit with the state of the local work branch.

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
#     controller axes: PY310 tools\remake\repack_apk.py axes --data <data.unity3d> --remake WT --out <data-axes.unity3d>, then the apk stage with that file
# 0b. the phone: install it (the owner accepts the Play Protect prompt). Over our own APK: adb install -r.
C:\platform-tools\adb.exe install -r dist\remake-phone\apk\GCG-Offline-v0.1.3-gcg2-b.apk

# 1. lua.u: the released script bundle plus our recipes, then the mock tests on the result
PY310 tools\remake\build_phone_update.py lua --apk APK --client-dir WT\release\client --hooks-only --english-title --offline-web --offline-links --tests --out dist\remake-phone\lua.u
#    --offline-links needs a client dir with patch_offline_links.py (Remake branch gcg2-web-cleanup, cards gcg2#24-26)

# 2. login atlas with the English sprites
C:\platform-tools\adb.exe pull FILES/ui_tx/ui_login.u dist\remake-phone\from-phone\ui_tx\ui_login.u
PY310 tools\remake\build_phone_update.py art --remake-atlas dist\remake-phone\from-phone\ui_tx\ui_login.u --en-atlas assets\Bundles\ui_tx\ui_login.u --out dist\remake-phone\extra\ui_tx\ui_login.u

# 3. server payload. Drive D: has no junctions, so the source goes to a folder on C: first:
git -C WT archive gcg2-phone-build-next server/src server/resources server/tsconfig.json server/tsconfig.build.json server/package.json | tar -x -C <C:\scratch>
python tools\remake\build_phone_update.py server --apk APK --server-dir <C:\scratch>\server --node-modules repos\GirlCafeGun-Remake\server\node_modules --remake WT --work <C:\scratch>\srv --out dist\remake-phone\payload.zip --web-pages --resources activity item

# 4. sign and pack on top of the release that is installed now
C:\platform-tools\adb.exe pull FILES/version.data dist\remake-phone\version.data.now
PY310 tools\remake\build_phone_update.py pack --apk APK --remake WT --lua dist\remake-phone\lua.u --extra dist\remake-phone\extra --payload dist\remake-phone\payload.zip --version-data dist\remake-phone\version.data.now --release-id <new id> --signing-dir .local\remake-signing --java C:\android-build\jdk\<jdk>\bin\java.exe --work dist\remake-phone\pack-work --out dist\remake-phone\<new id>.gcgupdate
#    when the installed release is one of ours, add: --base-manifest dist\remake-phone\manifest-<installed id>.json
#    pass --extra and --payload only when those parts changed
#    a bundle path that is not a row of the base manifest stops the pack (a mistyped folder or case);
#    add --allow-new-bundle only when a new bundle is meant (it prints one warning line per added bundle)
#    --require-entry <name in payload.zip> (repeatable) stops the pack when the payload lacks that entry,
#    for example --require-entry resources/web/notice/index.html

# 5. to the phone and apply (the game shows its title screen)
C:\platform-tools\adb.exe push dist\remake-phone\<new id>.gcgupdate FILES/updates/
python tools\remake\apply_update_on_phone.py --package-name <new id>.gcgupdate --fingerprint dbce3bad83600b1a7540b07d4eb734ac6065ee2e90b589ef3cffcdce8ee6dac3
```

Rules of the update chain:
- A package applies only on the release it names as its base. The installed id is now `gcg2-0.1.3-20`; the next
  package needs `--base-manifest dist\remake-phone\manifest-gcg2-0.1.3-20.json`. `dist\` is not in git: keep that file.
- 2026-11-16 16:34: release `gcg2-0.1.3-21` is APPLIED (save backed up first, `saves-backup\remake\20261116-163219-before-r21`); the server logs `timeZone Asia/Tbilisi`, `utcOffsetMinutes 240`, the phone's own zone: server only (bug sweep, `gcg2-server-fixes` merged
  into `gcg2-phone-build-main` as `b617fac`; 479 tests green), Lua bundle = `lua-r20.u` (same sha256 as release
  20, so the pad hand-over change gcg2#52 is not in it), payload `payload-r21.zip`. The next package
  needs `--base-manifest dist\remake-phone\manifest-gcg2-0.1.3-21.json`.
- 2026-11-16 18:28 (+04): release `gcg2-0.1.3-22` is APPLIED (save backed up first, `saves-backup\remake\20261116-182252-before-r22`; server started clean): server only, on top of release 21.
  `gcg2-phone-build-main` tip `38bf382` adds the merges of `gcg2-error-replies` (#48), `qwen-59-formation-cards`
  (#50 live event achievements + type 59), `gcg2-cafe-seats` (#74 default cafe furniture), `gcg2-task-change`
  (#49 client task write allowlist), `gcg2-guide-missions` (#53, one conflict in the girl gift path: both sides
  kept), `qwen-57h-http-host` (#57) and `gcg2-server-fixes` `8835983` (test timing); 600 tests green. Lua =
  `lua-r20.u`; payload `payload-r22.zip` (server resources now also `cafe`, for `ncafedefautitems.txt`).
- 2026-11-16 19:19 (+04): release `gcg2-0.1.3-23` is APPLIED (the stricter `apply_update_on_phone.py` read the
  installed id back: 22 -> 23). Server AND Lua, on top of release 22. Lua = `lua-r23.u`, built with
  `--hooks-only --english-title --offline-web --tests` from `repos/GirlCafeGun-Remake-wt-phone/release/client`
  (all four mock suites true): it carries the pad hand-over (#52) and the pad scroll limit (#57). The login timeout
  of #57 changes `release_login.lua`, which `--hooks-only` does not apply: not on the phone. Phone build tip
  `fa85ce9` = the merges below plus `gcg2-bug-sweep` (the PR branch: notices with the local reset time, comments)
  and `gcg2-client-leftovers`; 633 tests green. Live check: `/notice.txt` shows the four notices and "reset every
  day at 00:00 (your device's time)". The next package needs
  `--base-manifest dist\remake-phone\manifest-gcg2-0.1.3-23.json`.
  Upstream pull request: zirenmidori/GirlCafeGun-Remake#8 from `fork/gcg2-bug-sweep` (server, save tool, notices).
  Earlier build of the same id, superseded and never applied: `gcg2-phone-build-main` tip `f90344f` adds the merges of `gcg2-decisions` (#54 permit 10-pull, #55 month card
  once per 30 days, #56 broken save falls back to the newest daily copy), `gcg2-server-leftovers` (#57 chapter
  awards through grantAwards, bounty 04:00 weekday), `gcg2-shop-groups` (#51) and `gcg2-cafe-achievements` (#59
  types 75 and 137; one conflict in the shop purchase: mission 108 counted before the task snapshot, one
  TASK_VALUE_RSP). 632 tests green. Lua = `lua-r20.u` (client fixes of #57 and #52 are still not in a release);
  payload `payload-r23.zip`.
- 2026-11-16 20:00 (+04): release `gcg2-0.1.3-24` is APPLIED (read back 23 -> 24): Lua only, on top of 23.
  `lua-r24.u` adds the dead-link recipe (`--offline-links`, Remake branch `gcg2-web-cleanup`, cards #24-#26: no
  rate window, the old wiki banner opens wiki.girl.cafe, the survey opens nothing, Settings hides Terms, Privacy,
  Support and three bilibili rows); five mock suites true. Phone build tip `1b5e1ed`. Just before it, the save was
  wiped with the save tool (Alex's request; backup `saves-backup\remake\20261116-195714-before-wipe`). The next
  package needs `--base-manifest dist\remake-phone\manifest-gcg2-0.1.3-24.json`.
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
- **Controller axes.** `repack_apk.py axes` adds 28 InputManager entries. Only the file `globalgamemanagers`
  inside `data.unity3d` is written again and only the InputManager object differs (asserted object by object).
  The C# build's `apk-build/patch_inputmanager.py` is not used here: it saves the whole container, which rewrote
  seven scene files of this APK. APK `GCG-Offline-v0.1.3-gcg2-b.apk`: sha256 `853427c1...`, installed 2026-11-14 22:18.
- **Combined server.** The Remake test suite on the combined branch: 435 passed, 2 skipped.
- **Release 10 (2026-11-15).** Branch `gcg2-phone-build-next` = `gcg2-phone-build` + `gcg2-activity-rewards` +
  `gcg2-offline-web` (conflicts in `release/client/build.py`, `patch_lua.py` and `server/docs/modules/README.md`:
  both sides kept). vitest: 83 files, 468 passed, 2 skipped; eslint, tsc and the build exit 0; 68 runtime modules.
  `lua-r10.u` (sha256 `3829f7b5...`): the controller, title and web-window bundle tests are true. `payload-r10.zip`
  (727 entries, with `resources/web`, `resources/activity` and `resources/item`) starts on the PC; `/notice.html`,
  `/web/notice/index.html`, `/web/maintenance/index.html`, `/web/offline/index.html` and `/notice.txt` answer 200.
  Package `gcg2-0.1.3-10.gcgupdate`: sha256 `9a83f447...`, base `gcg2-0.1.3-9`.
- **Menu navigation with the pad (2026-11-15, card gcg2#37).** Remake branch `gcg2-controller-menus` (from
  `origin/main`, local, not pushed): `release/client/gamepad_menu.lua` in `UI.lua` (focus frame over the game's
  own buttons, A/B/LB/RB, right-stick scroll, story advance, optional cursor on Select), the fight layer on a
  real-time timer and yielding to it. Its three commits are cherry-picked onto `gcg2-phone-build-next`
  (`build.py` conflict: both proof lines kept). `lua-r13.u` (sha256 `d86383921bc03bc9...`) from that worktree:
  the controller, menu, title and web-window bundle tests are true. Packed with `--lua` only (no `--extra`, no
  `--payload`). The phone's `version.data` (00:41) did not change with releases 11 and 12 (server only).
  - Release `gcg2-0.1.3-13` (sha256 `e295839c...`, applied 17:37): the injected `KEYCODE_BUTTON_A` showed the
    focus frame on the title (on Update): the menu layer and its xLua `List(RaycastResult)` raycast run on the phone.
    The title's "Tap Screen to Start" (`PnlBG/BtnLogin`, a full-screen Button) was not reachable.
  - Release `gcg2-0.1.3-14` (`lua-r14.u`, sha256 `553ff10b...`, applied): a full-screen window button counts as the
    main action. Still on Update: the client's start button is not the window root.
  - Release `gcg2-0.1.3-15` (`lua-r15.u` sha256 `8cdeb75e...`, package `5ee8d35e...`, base 14): any full-screen
    Button not named like a backdrop is the main action. Pushed to `updates/`; `apply_update_on_phone.py` stopped
    ("not on screen: UPDATES IN GAME FOLDER") and the game went on into the prologue story. Applied 17:47 from the title: one injected A puts the frame on the screen edges ("Tap Screen to Start" focused).
  - Release `gcg2-0.1.3-16` (`lua-r16.u` sha256 `1dd67e05...`, package `facb9484...`, base 15, applied 18:00 from
    the title). Source: Remake branch `gcg2-phone-build-main` = `origin/main` `ffe59ea` (pull requests 1 to 6
    merged) + `gcg2-controller-menus`. Packed with `--lua` only: the server is unchanged. Fix: on 15 a white
    100 x 100 square showed bottom-left in the story. `makeImage` in `gamepad_menu.lua` made the overlay images
    active at Unity's default size on the bottom-left anchor, and the cursor images stay unplaced until the cursor
    is on. Now each image starts hidden (Remake commit `868d3c8`; the new check in `test_gamepad_menu.py` fails on
    the old code). On the phone after one injected A: frame on the title edges, corner clear; the installed
    `lua.u` size equals `lua-r16.u`.
  - Releases `gcg2-0.1.3-17` to `-20` (2026-11-15, `--lua` only, from `gcg2-phone-build-main`): on the snow
    title Irene (Spine bones `ailin_zx`, `ailin_50`, `ailin_55` of `girl1002_2da01`) stood over the dirt path and
    looked as if she floated. `title_screens.lua` now sets those bones' setup-pose y before `idle` plays.
    17: the model object gave no `Skeleton` (log `snow: bones not set`). 18: more routes to the skeleton; it
    worked, but Irene left the screen: the client imports the skeleton at a scale, and the y was in file units.
    19: the scale comes from Kaluo's root `kaluo_zx` (file y 580.84), lift 100: about 45 px, feet still on the
    dirt. 20 (`lua-r20.u` sha256 `4ed481cb...`, package `bb051f98...`, base 19): lift 250, feet on the snow
    above the dirt (screenshot `dist\remake-phone\snow-r20.png`). Remake commits `5a70365`, `3b5913f`.
    `apply_update_on_phone.py` cannot scroll the package list: with seven packages in `updates/` it stopped
    ("not on screen"). The applied packages 13 to 18 were removed from the phone (copies stay in `dist`).
  - On release 14, in the prologue (`UI_Cartoon`), one injected A advanced the dialogue by one line.
  - adb `input keyevent` reaches Unity as a pad button only for `KEYCODE_BUTTON_A` here; `keycombination`
    L3+R3 and `KEYCODE_DPAD_*` gave no visible effect. D-pad, B, LB/RB and the cursor need the real pad.
  - `[pad] menu: started` is not in logcat: it is printed at the first `UI.Open`, before the client turns on Lua
    logging [INFER].
- **Not possible:** a full run of Remake's `patch_lua.py` on `assets/lua.u.orig` of the release APK. That file is
  not the input their build pins: `patch_selectors` stops on its first anchor. So the release cannot be
  reproduced from the APK alone, and the hooks-only way is the one we use.

## Saves: the save tool (2026-11-15)

Saves are files that a PC tool moves; nothing in the game code handles them (the owner's rule). The save is one
file in the private storage of the app, `files/gcg-server/data/state.json`, so the tool needs `adb shell run-as`,
and that needs an APK with `android:debuggable`. The manifest of the Remake APK holds the attribute with the value
false; `repack_apk.py apk --debuggable` changes that one value (4 bytes; `aapt2 dump xmltree` differs in one line).
APK `GCG-Offline-v0.1.3-gcg2-c.apk` (sha256 `b3d0cd87...`), installed over the earlier one with `adb install -r`
(Play Protect prompt, data kept). Side effect: every PC with adb access to the phone can read the app's files.

**APK `gcg2-d` (2026-11-16, card gcg2#27, built, NOT installed).** `GCG-Offline-v0.1.3-gcg2-d.apk`, sha256
`edcd4c3a7c872679cb1a3b3468710daf41b6ec336189bade9b460429f5263d5e`, 404,008,143 bytes. Made from `gcg2-c` (English
intro, controller axes and debuggable stay) with the `sdk-off` stage: the GameObject `u3dautosdk` of `level0` is
inactive (no UAutoSDK listener on port 13000) and `Crasheye.init(Context, String, String)` returns false at once (no
Crasheye session or crash upload). Checks on the output: `apksigner verify` (v2, v3; our certificate `b2ef7cc0...`, the
same as `gcg2-c`), `zipalign -c`, versionCode 10141, `application-debuggable`, the manifest byte for byte the same,
only `data.unity3d` (1 byte of the unpacked container) and `classes.dex` (3 code bytes and the header) differ,
28 `gcgpad_a` axes, `dexdump` "Checksum verified" and `d8` reads the dex. Install with `adb install -r` (data kept).
Installed 2026-11-16; the second capture showed Unity's own analytics still sending (`docs/08` section 7).

**APK `gcg2-e` (2026-11-16, card gcg2#27, built, NOT installed).** `GCG-Offline-v0.1.3-gcg2-e.apk`, sha256
`949451984531a7465add25b77e926df31a6362ae888e6b8258be452494343991`, 404,008,143 bytes. The same commands as `gcg2-d`
(`sdk-off` now also turns Unity analytics off): `gcg2-d` plus `UnityConnectSettings.m_Enabled`,
`UnityAnalyticsSettings.m_InitializeOnStartup` and `PlayerSettings.submitAnalytics` false (3 more bytes of
`globalgamemanagers`; 4 unpacked bytes differ from `gcg2-c`). `classes.dex` is the one of `gcg2-d`. Same checks as
`gcg2-d`, all passed.

```
PY310 tools\remake\repack_apk.py sdk-off --apk dist\remake-phone\apk\GCG-Offline-v0.1.3-gcg2-c.apk --remake <Remake checkout> --out-dir <dir>
PY310 tools\remake\repack_apk.py apk --apk dist\remake-phone\apk\GCG-Offline-v0.1.3-gcg2-c.apk --data <dir>\data.unity3d --dex <dir>\classes.dex --signing-dir .local\remake-signing --build-tools C:\android-build\bt\android-15 --java-home C:\android-build\jdk\<jdk> --out dist\remake-phone\apk\GCG-Offline-v0.1.3-gcg2-d.apk
```

```
python tools\remake\save_tool.py status             # is there a save, is it on the PC, the PC saves
python tools\remake\save_tool.py backup --label L   # phone -> saves-backup\remake\<time>-L\ (the game may run)
python tools\remake\save_tool.py push <save>        # PC -> phone; <save> = folder name, a part of it, or a .json file
python tools\remake\save_tool.py wipe               # no save on the phone; the game makes a new one
```

- `push` and `wipe` stop the game and copy the phone's save to the PC first (skipped when that save is already
  there, by hash). `push` copies as the app and renames, then reads the file back and compares it.
- Both remove the server's daily copies on the phone (`data/backups`), so two saves do not mix; `backup` copies
  them to `phone-daily-copies\`.
- Tried on the phone 2026-11-15 01:08: backup (6,958 bytes); push of the older save, after which the server log
  says `persistence.loaded`; wipe, after which it says `persistence.created`. Not tried: a push while the phone is
  locked, and a save from another release of the server.
- Remake pull request 6 (`gcg2-save-tool`) holds the same tool as `tools/save-tool/save_tool.py`, a helper
  `playtest_apk.py` (the debuggable flag alone, signed with the tester's key) and `test_save_tool.py` (9 checks,
  no phone). That version ran on the phone too (01:14): status, backup, push, wipe.
- History: release 11 had a reset-on-request step in the server (wrong place); release 12 removed it. The save it
  set aside is on the PC as `20261115-005433-set-aside-by-reset`.

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

- Release `gcg2-0.1.3-12` (2026-11-15 01:05): server payload only, the reset step removed (727 entries, 68 runtime
  modules; combined branch: vitest 83 files, 468 passed, 2 skipped). Applied; the update screen stayed in front
  ("No published update is available for data release gcg2-0.1.3-12"), RETURN TO GAME goes back.
- Release `gcg2-0.1.3-11` (2026-11-15 00:53): server payload only (728 entries, 69 runtime modules); combined
  branch: vitest 84 files, 473 passed, 2 skipped. Applied through the Update screen; the game restarted by itself.
  Save reset at 00:54: marker written, app started, title reached (`[title] snow`), the marker was gone and
  `/notice.html` answered 200. The moved save and the server log are private: not read.
- Release `gcg2-0.1.3-10` (2026-11-15 00:41): applied through the Update screen. The game closed and did not start
  again by itself (`apply_update_on_phone.py` ended with "the game did not come back"); started again it reaches
  the title (`[title] hall`). `files/lua.u` is `3829f7b5...`. Through `adb forward` the server on the phone answers
  200 for `/notice.html`, `/web/notice/index.html`, `/web/maintenance/index.html`, `/web/offline/index.html` and
  `/notice.txt`; `/` stays 404. Not seen: the three web windows and any Claim button (the save is in the
  prologue). The two `Lib:Dump` tracebacks of `pldgecommon.lua` at the start are older than this release (they
  are in the logs of 2026-11-14 too).
- Release `gcg2-0.1.3-9` on the APK with the controller axes (23:40): the game starts and reaches the title; 13
  bundles are in `files/update/`, both theme songs in `files/wwisedata/` (the hash of the English one equals our
  file); five starts logged sky, shards, sky, sky, snow; no error line names `update/` or a theme song. Whether
  the client uses the `update/` bundles was not seen. The controller was not tried with a pad.
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
   If upstream merged one of our pull requests, drop that part. The first pack on a new APK adds the 13
   `update/` bundles from EN 1.0.7, which are not in that APK's manifest: pass `--allow-new-bundle` there.
3. Open question: whether the app accepts a full official data set over our release id without a reinstall.
   Check it before the first real update; the save is at risk only on an uninstall.

The weekly scheduled task `gcg2-weekly-upstream-check` reports when this is needed.
