#!/usr/bin/env python3
"""Builds and switches the two content sets of the offline build.

  build5  the EN v1.0.9 OBB as shipped: main story to chapter 12, banners to July 2022
  late    the last EN hot update (build 179, the files in assets/Bundles): chapters 13-16, banners to 2023,
          official English text for most of what build 5 left in Chinese

The active set is always in the same places, so every other script works unchanged:
  server/setting/                      tables the server reads
  assets/device_assets/overrides/      lua.u, lang.u, (setting.u), versioncrc.json, ... pushed into files/
  assets/device_assets/version.data    bundle table pushed into files/
  assets/device_assets/tableset.txt    name of the active set (missing = build5)
The other set is parked in server/setting.<name>/ and assets/device_assets/sets/<name>/.

  python -I tools/tableset.py status
  python -I tools/tableset.py build-late [--force]   make the parked late set from OBB + Bundles + the build5 patches
  python -I tools/tableset.py use late|build5        swap the parked set in (then rebuild the APK and the data pack)

build-late keeps our work: Lua scripts we patched are merged with the build-179 scripts (3-way, git merge-file),
our translations stay where build 179 still has the build-5 text. Details: docs/12-LATE-CONTENT.md.
"""
import datetime
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

import UnityPy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_setting  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLES = os.path.join(ROOT, "assets", "Bundles")
DEV = os.path.join(ROOT, "assets", "device_assets")
SETTING = os.path.join(ROOT, "server", "setting")
OVERRIDES = os.path.join(DEV, "overrides")
VERSION = os.path.join(DEV, "version.data")
MARKER = os.path.join(DEV, "tableset.txt")
CHANGED = os.path.join(DEV, "late_changed_bundles.txt")
SETS = ("build5", "late")
KEEP = ("CartoonFileId.txt", "CharacterCard.txt", "Rune.txt", "Weapon.txt")  # same in both builds, not in the text tables
ROTATION_START = 1577836800  # 2020-01-01, as in the build5 rotation
ROTATION_END = 1893456000    # 2030-01-01
CYCLE_START = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)
CYCLE_DAYS = 15              # the live length of one period of a rotating pool (gacha.txt, pool 43)
swap = extract_setting.swap


def parked_setting(name):
    return os.path.join(ROOT, "server", "setting." + name)


def parked(name, *parts):
    return os.path.join(DEV, "sets", name, *parts)


def active():
    if os.path.exists(MARKER):
        return open(MARKER, encoding="utf-8").read().strip()
    return "build5"


def obb_path():
    d = os.path.join(ROOT, "assets", "obb")
    return os.path.join(d, [f for f in os.listdir(d) if f.startswith("main.") and f.endswith(".obb")][0])


def obb_read(name):
    with zipfile.ZipFile(obb_path()) as z:
        return z.read("assets/" + name)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def build5_dir(kind):
    """Where the build5 patches are right now: active, or parked after `use late`."""
    if active() == "build5":
        return {"setting": SETTING, "overrides": OVERRIDES}[kind]
    return {"setting": parked_setting("build5"), "overrides": parked("build5", "overrides")}[kind]


# ---------------------------------------------------------------- Lua

def scripts(env):
    out = {}
    for o in env.objects:
        if o.type.name == "TextAsset":
            a = o.read()
            s = a.m_Script
            out[a.m_Name] = (a, s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s))
    return out


def merge3(name, ours, base, theirs):
    with tempfile.TemporaryDirectory() as t:
        paths = []
        for label, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            p = os.path.join(t, label + "_" + name)
            write(p, data)
            paths.append(p)
        r = subprocess.run(["git", "merge-file", "-p"] + paths, capture_output=True)
        if r.returncode != 0:
            sys.exit(f"{name}: our patch and build 179 change the same lines; merge it by hand "
                     f"(git merge-file exit {r.returncode})")
        return r.stdout


def build_lua(dest):
    base = {n: b for n, (_, b) in scripts(UnityPy.load(swap(obb_read("lua.u")))).items()}
    ours = {n: b for n, (_, b) in scripts(UnityPy.load(swap(read(os.path.join(build5_dir("overrides"), "lua.u"))))).items()}
    env = UnityPy.load(swap(read(os.path.join(BUNDLES, "lua.u"))))
    theirs = scripts(env)
    kept, merged = [], []
    for name, mine in ours.items():
        if mine == base.get(name):
            continue
        if name not in theirs:
            sys.exit(f"{name}: patched by us but not in build 179")
        asset, late = theirs[name]
        if late == base.get(name):
            new = mine
            kept.append(name)
        else:
            new = merge3(name, mine, base[name], late)
            merged.append(name)
        asset.m_Script = new.decode("utf-8", "surrogateescape")
        asset.save()
    out = swap(env.file.save(packer="original"))
    write(dest, out)
    print(f"lua.u: {len(theirs)} scripts, {len(kept)} of ours carried over, {len(merged)} merged ({', '.join(merged)})")
    return zlib.crc32(out)


# ---------------------------------------------------------------- language table

def lang_object(env):
    for o in env.objects:
        if o.type.name == "MonoBehaviour":
            return o
    sys.exit("lang.u: no language object")


def lang_parse(d):
    pos = 28  # MonoBehaviour header: GameObject, enabled, script

    def text():
        nonlocal pos
        n = struct.unpack_from("<i", d, pos)[0]
        pos += 4
        v = d[pos:pos + n]
        pos += (n + 3) // 4 * 4
        return v

    text()  # object name (en_US)
    head = d[:pos]
    n = struct.unpack_from("<i", d, pos)[0]
    pos += 4
    keys = [text() for _ in range(n)]
    n = struct.unpack_from("<i", d, pos)[0]
    pos += 4
    values = [text() for _ in range(n)]
    if pos != len(d) or len(keys) != len(values):
        sys.exit("lang.u: unexpected layout")
    return head, keys, values


def lang_pack(head, keys, values):
    def texts(items):
        out = [struct.pack("<i", len(items))]
        for v in items:
            out.append(struct.pack("<i", len(v)) + v + b"\0" * (-len(v) % 4))
        return b"".join(out)
    return head + texts(keys) + texts(values)


def build_lang(dest):
    _, bk, bv = lang_parse(lang_object(UnityPy.load(obb_read("lang.u"))).get_raw_data())
    _, ok, ov = lang_parse(lang_object(UnityPy.load(read(os.path.join(build5_dir("overrides"), "lang.u")))).get_raw_data())
    env = UnityPy.load(read(os.path.join(BUNDLES, "lang.u")))
    obj = lang_object(env)
    head, keys, values = lang_parse(obj.get_raw_data())
    base, ours = dict(zip(bk, bv)), dict(zip(ok, ov))
    carried = official = 0
    for i, k in enumerate(keys):
        if k in base and ours.get(k, base[k]) != base[k]:
            if values[i] == base[k]:
                values[i] = ours[k]   # build 179 still has the build-5 text: keep our translation
                carried += 1
            else:
                official += 1         # build 179 has its own (official) text: use it
    obj.set_raw_data(lang_pack(head, keys, values))
    out = env.file.save(packer="original")
    check = lang_parse(lang_object(UnityPy.load(out)).get_raw_data())
    if check[1] != keys or check[2] != values:
        sys.exit("lang.u: the saved bundle does not read back")
    write(dest, out)
    print(f"lang.u: {len(keys)} entries ({len(keys) - len(bk)} new), {carried} of our translations kept, "
          f"{official} replaced by the build-179 text")


# ---------------------------------------------------------------- gacha rotation

def stamp(text):
    """202207150400 or 20770731085959 -> comparable integer (the table mixes both lengths)."""
    return int(text.strip().ljust(14, "0")) if text.strip().isdigit() else 0


def build_rotation(setting_dir):
    rows = [r.split("\t") for r in read(os.path.join(setting_dir, "gacha.txt")).decode("utf-8").splitlines()]
    col = {n: i for i, n in enumerate(rows[2])}
    segments = {}
    for r in rows[3:]:
        if len(r) > col["Pool"] and r[0].strip().isdigit() and r[col["Type"]].strip() in ("0", "1") and int(r[0]) > 0:
            segments.setdefault((int(r[col["Type"]]), int(r[0])), []).append(r)
    entries = []
    cycling = []
    for (typ, pid), segs in sorted(segments.items()):
        ends = [stamp(s[col["Time"]].strip("{} ").split(",")[-1]) for s in segs]
        starts = [stamp(s[col["Time"]].strip("{} ").split(",")[0]) for s in segs]
        contiguous = len(segs) > 2 and all(starts[i + 1] == ends[i] for i in range(len(segs) - 1))
        if contiguous and pid != 1:
            # a pool that changed its featured cards every period: run the periods one after another, forever
            t = CYCLE_START
            i = 0
            while t.timestamp() < ROTATION_END:
                nxt = min((t + datetime.timedelta(days=CYCLE_DAYS)).timestamp(), ROTATION_END)
                entries.append({"Type": typ, "Id": pid, "Segment": i % len(segs) + 1, "Start": int(t.timestamp()), "End": int(nxt)})
                t += datetime.timedelta(days=CYCLE_DAYS)
                i += 1
            cycling.append(pid)
        else:
            # the newest period of the pool (for the standard pool: the one that holds every earlier banner card)
            newest = max(range(len(segs)), key=lambda i: (ends[i], i))
            entries.append({"Type": typ, "Id": pid, "Segment": newest + 1, "Start": ROTATION_START, "End": ROTATION_END})
    write(os.path.join(setting_dir, "gacha-rotation.json"),
          json.dumps({"Enabled": True, "Entries": entries}, indent=1).encode("utf-8"))
    print(f"gacha-rotation.json: {len(segments)} pools open ({sum(1 for k in segments if k[0] == 1)} character, "
          f"{sum(1 for k in segments if k[0] == 0)} weapon), cycling every {CYCLE_DAYS} days: {cycling}")


# ---------------------------------------------------------------- commands

def build_late(force):
    sdir, odir, vfile = SETTING, OVERRIDES, VERSION
    if active() != "late":
        sdir, odir, vfile = parked_setting("late"), parked("late", "overrides"), parked("late", "version.data")
    for p in (sdir, odir):
        if os.path.exists(p):
            if not force:
                sys.exit(f"{p} exists; pass --force to rebuild it (gacha-rotation.json and overrides edits are lost)")
            shutil.rmtree(p)

    # 1. server tables
    tables = extract_setting.tables(extract_setting.read_source("late"))
    for rel, data in tables.items():
        write(os.path.join(sdir, rel.replace("/", os.sep)), data)
    for f in KEEP:
        shutil.copyfile(os.path.join(build5_dir("setting"), f), os.path.join(sdir, f))
    print(f"server tables: {len(tables)} files + {len(KEEP)} kept -> {os.path.relpath(sdir, ROOT)}")
    build_rotation(sdir)

    # 2. files pushed into the game's files/ folder
    b5 = build5_dir("overrides")
    for dp, _, fs in os.walk(b5):
        for f in fs:
            rel = os.path.relpath(os.path.join(dp, f), b5)
            if rel not in ("lua.u", "lang.u", "versioncrc.json"):
                write(os.path.join(odir, rel), read(os.path.join(dp, f)))
    lua_crc = build_lua(os.path.join(odir, "lua.u"))
    build_lang(os.path.join(odir, "lang.u"))
    setting_u = read(os.path.join(BUNDLES, "setting.u"))
    write(os.path.join(odir, "setting.u"), setting_u)
    # the game decrypts lua.u and setting.u only when their CRC32 matches this file (docs/05-PHONE-PORT.md 3.1)
    write(os.path.join(odir, "versioncrc.json"),
          json.dumps({"CRC": {"lua.u": str(lua_crc), "setting.u": str(zlib.crc32(setting_u))}}, separators=(",", ":")).encode())
    write(vfile, read(os.path.join(BUNDLES, "version.data")))
    print(f"overrides -> {os.path.relpath(odir, ROOT)}; bundle table (build 179) -> {os.path.relpath(vfile, ROOT)}")

    # 3. bundles the OBB has in an older form: in the late set the build-179 copies must go to the phone too
    have = set()
    for dp, _, fs in os.walk(odir):
        have.update(os.path.relpath(os.path.join(dp, f), odir).replace("\\", "/") for f in fs)
    changed = []
    with zipfile.ZipFile(obb_path()) as z:
        for info in z.infolist():
            rel = info.filename[len("assets/"):]
            p = os.path.join(BUNDLES, rel.replace("/", os.sep))
            if not info.filename.startswith("assets/") or not rel.endswith(".u") or rel in have or not os.path.isfile(p):
                continue
            if os.path.getsize(p) != info.file_size or zlib.crc32(read(p)) != info.CRC:
                changed.append(rel)
    write(CHANGED, ("\n".join(sorted(changed)) + "\n").encode())
    size = sum(os.path.getsize(os.path.join(BUNDLES, c.replace("/", os.sep))) for c in changed)
    print(f"{len(changed)} bundles differ from the OBB copy ({size / 2**20:.0f} MB) -> {os.path.relpath(CHANGED, ROOT)}")


def use(name):
    if name not in SETS:
        sys.exit("unknown set: " + name)
    cur = active()
    if cur == name:
        print("already active:", name)
        return
    moves = [(SETTING, parked_setting(cur), parked_setting(name)),
             (OVERRIDES, parked(cur, "overrides"), parked(name, "overrides")),
             (VERSION, parked(cur, "version.data"), parked(name, "version.data"))]
    for act, out, inn in moves:
        if not os.path.exists(inn):
            sys.exit(f"missing {inn}" + (" (run build-late first)" if name == "late" else ""))
        if os.path.exists(out):
            sys.exit(f"{out} exists already; the parked {cur} set would be overwritten")
    done = []
    try:
        for act, out, inn in moves:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            os.rename(act, out)
            done.append((out, act))
            os.rename(inn, act)
            done.append((act, inn))
    except OSError as e:
        for src, dst in reversed(done):
            os.rename(src, dst)
        sys.exit(f"could not switch (a file is open?): {e}; nothing changed")
    write(MARKER, (name + "\n").encode())
    print(f"active set: {name}. Rebuild the APK (server tables are inside it) and the data pack / phone sync.")


def status():
    print("active set:", active())
    for n in SETS:
        if n != active():
            ok = all(os.path.exists(p) for p in (parked_setting(n), parked(n, "overrides"), parked(n, "version.data")))
            print(f"parked {n}: {'ready' if ok else 'not built'}")
    with open(VERSION, "rb") as f:
        version, build = struct.unpack("<ii", f.read(8))
    print(f"active bundle table: version {version}, build {build}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "status":
        status()
    elif cmd == "build-late":
        build_late("--force" in sys.argv)
    elif cmd == "use" and len(sys.argv) > 2:
        use(sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
