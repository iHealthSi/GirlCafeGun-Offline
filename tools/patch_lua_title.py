#!/usr/bin/env python3
"""Places the title-screen rotation (tools/lua/TitleScreens.lua) in UI_Login.lua inside the client Lua bundle.

The login screen then shows one title at each start, chosen at random among the titles whose art the client can
load: hall, sky, snow, shards. The module goes in once, before Load2DBG (between marker lines), and the language
test of Load2DBG becomes one call to it. The stock hall branch is not edited. A lua.u that still carries the first
two-title edit (docs/05-PHONE-PORT.md 3.2, made by hand) is converted. Re-running replaces the module with the
current tools/lua/TitleScreens.lua, so edit that file and run this again.

  usage: python -I tools/patch_lua_title.py [lua.u in] [lua.u out] [versioncrc.json]
  default: assets/device_assets/overrides/lua.u (in place) + its versioncrc.json
The parked set has its own copy: assets/device_assets/sets/<name>/overrides/lua.u and versioncrc.json.
lua.u is swap-encrypted (docs/05 section 3.1); the CRC32 of the encrypted file goes into versioncrc.json, or the
game rejects lua.u. The same module is the client recipe release/client/title_screens.lua of GirlCafeGun-Remake.
"""
import json, os, sys, zlib
import UnityPy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVR = os.path.join(ROOT, "assets", "device_assets", "overrides")
MODULE = os.path.join(ROOT, "tools", "lua", "TitleScreens.lua")
SEED = 0x166920ED
NAME = "UI_Login.lua"
BEGIN, END = b"-- >>> gcg2#33 title screens (tools/patch_lua_title.py)", b"-- <<< gcg2#33 title screens"
HEAD = b"function tbClass:Load2DBG()"
STOCK_TEST = b"\tif self:IsUS() then "
TEST = b"\tif TitleScreens.Choose(self) then "
# the first edit, made by hand in the built lua.u: five lines in place of the language test
OLD_EDIT = (b"\t-- offline build: pick one of the two title screens at random on every launch",
            b"\tlocal useHall = U3D.Random.value < 0.5",
            b"\tlocal spine = self:FindObject(\"Spine\")",
            b"\tif spine then spine:SetActive(not useHall) end",
            b"\tif useHall then ")
# stock lines the module and this patch rely on, each exactly once
NEEDS = (b"function tbClass:IsUS()", b"function tbClass:BackgroundAdapter()", b"self:Load2DBG()",
         b'\t\tself:FindObject("PnlBGEffect/eftParent4"):SetActive(false);',
         b'\t\tself:FindObject("PnlBGEffect/Image3"):SetActive(false);')


def swap(data):
    d = bytearray(data)
    for i in range(2, len(d), 4):
        j = i - 1
        if SEED % j < j // 3:
            d[j], d[i] = d[i], d[j]
    return bytes(d)


def one(b, what):
    if b.count(what) != 1:
        sys.exit("UI_Login.lua: %r found %d times (want 1)" % (what[:60], b.count(what)))


def patch(b, module):
    nl = b"\r\n" if b"\r\n" in b else b"\n"
    body = module.replace(b"\r\n", b"\n").rstrip(b"\n")
    if not body.endswith(b"\nTitleScreens = P"):
        sys.exit("TitleScreens.lua must end with 'TitleScreens = P'")
    # the do-block keeps the module's locals out of the scope of the stock script below it
    block = (BEGIN + b"\nlocal TitleScreens\ndo\n" + body + b"\nend\n" + END + b"\n").replace(b"\n", nl)
    if BEGIN in b:   # refresh the module, keep the call
        one(b, BEGIN); one(b, END)
        a = b.index(BEGIN); e = b.index(END, a)
        e = b.index(b"\n", e) + 1
        status, b = "module refreshed", b[:a] + block + b[e:]
    else:
        if b"TitleScreens" in b:
            sys.exit("UI_Login.lua already uses the name TitleScreens")
        old = HEAD + nl + nl.join(OLD_EDIT) + nl
        status = "patched"
        if old in b:
            b = b.replace(old, HEAD + nl + STOCK_TEST + nl)
            status = "two-title edit converted"
        stock = HEAD + nl + STOCK_TEST + nl
        one(b, stock)
        b = b.replace(stock, block + HEAD + nl + TEST + nl)
    one(b, block + HEAD + nl + TEST + nl)
    for line in NEEDS:
        one(b, line)
    return b, status


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OVR, "lua.u")
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    crcfile = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(dst)), "versioncrc.json")
    module = open(MODULE, "rb").read()
    env = UnityPy.load(swap(open(src, "rb").read()))
    status = None
    for o in env.objects:
        if o.type.name != "TextAsset":
            continue
        a = o.read()
        if a.m_Name != NAME:
            continue
        s = a.m_Script
        b = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
        nb, status = patch(b, module)
        if patch(nb, module)[0] != nb:
            sys.exit("UI_Login.lua: a second pass changes the script")
        try:   # syntax check when lupa is installed
            from lupa.lua53 import LuaRuntime
            LuaRuntime().execute("assert(load(...))", nb.decode("utf-8"))
        except ImportError:
            pass
        if nb == b:
            print("UI_Login.lua: already up to date"); return
        a.m_Script = nb.decode("utf-8", "surrogateescape")
        a.save()
    if status is None:
        sys.exit("UI_Login.lua not found in the bundle")
    out = swap(env.file.save(packer="original"))
    open(dst, "wb").write(out)
    crc = zlib.crc32(out)
    if os.path.exists(crcfile):
        j = json.load(open(crcfile, encoding="utf-8-sig"))
        j["CRC"]["lua.u"] = str(crc)
        json.dump(j, open(crcfile, "w", encoding="utf-8"), separators=(",", ":"))
    print("UI_Login.lua:", status, "->", dst, len(out), "bytes, CRC32", crc, "| crc file:", crcfile if os.path.exists(crcfile) else "none")


if __name__ == "__main__":
    main()
