Files pushed into the game's files folder (/sdcard/Android/data/com.biligameglobal.girlcafegungp/files/) on top of the OBB.
assets\sync_phone.ps1 installs them (non-root phones).

- lang.u             en_US language table of the active set (assets\device_assets\tableset.txt).
                     Late set (active since 2026-11-14): the build-179 table with official English, plus 2,691 of our
                     translations and 22 new keys. Build-5 set (sets\build5\overrides\lang.u): the OBB table with
                     the 16,186 values the official English build left in Chinese (stories, events, UI, items,
                     skills) translated to English.
- lua.u              OBB lua.u with: title rotation in UI_Login (hall, sky, snow, shards; a title whose art does not load
                     is left out; tools/patch_lua_title.py, docs/05-PHONE-PORT.md 3.2), and 65 hard-coded
                     on-screen Chinese strings translated. Re-encrypted with Game.BundleEncrypt (seed 0x166920ED).
- setting.u          OBB setting.u (server/client table bundle) of the active set; see docs/12-LATE-CONTENT.md.
- versioncrc.json    CRC32 of the patched lua.u; the game rejects lua.u if this does not match. Always ship with lua.u.
- ui/ui_login_prefab.u  build-179 title prefab (4-girl Spine off) with English button labels and best-fit text.
- lua.u also: UI_Fight.lua carries the gamepad layer (tools/lua/GamepadFight.lua, injected by tools/patch_lua_gamepad.py; docs/11-CONTROLLER.md).
- lua.u also: web windows use local pages (Notice -> local server /notice.html, server-error text embedded;
  tools/patch_lua_offline_web.py; docs/08-ONLINE-RESOURCES.md).
