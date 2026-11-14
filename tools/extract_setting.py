#!/usr/bin/env python3
"""Extracts the game config tables from a setting.u bundle into a server setting directory.

The server reads plain .txt tables (server/setting). They come from the client bundle setting.u:
  build 5   = the copy inside the OBB (EN v1.0.9 as shipped: main story to chapter 12, banners to July 2022)
  build 179 = assets/Bundles/setting.u (last EN hot update: chapters 13-16, banners to 2023)

Layout rules (they reproduce the existing server/setting byte for byte from the OBB copy):
  - every TextAsset is written as <m_Name>.txt in bundle object order; a later table with the same name
    (compared without case, as on Windows) replaces the earlier one and keeps the first file name
  - every table whose file name is used more than once is also written to _scoped/<path below settinggen/>
  - line ends are CRLF
  - ItemList.txt comes from the ItemList ScriptableObject in the same bundle (the game has no text table for it).
    CharacterCard, Rune and Weapon are the same bytes in build 5 and build 179, so the directory keeps its copies.

  usage: python -I tools/extract_setting.py <obb|late|path to setting.u> <output dir> [--compare <dir>]
  --compare lists the differences against an existing directory and writes nothing.
See docs/12-LATE-CONTENT.md.
"""
import collections
import os
import sys
import zipfile

import UnityPy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 0x166920ED
PREFIX = "assets/_game/settinggen/"


def swap(data):
    """Game.BundleEncrypt: the routine is its own inverse (docs/05-PHONE-PORT.md section 3.1)."""
    d = bytearray(data)
    for i in range(2, len(d), 4):
        j = i - 1
        if SEED % j < j // 3:
            d[j], d[i] = d[i], d[j]
    return bytes(d)


def read_source(source):
    if source == "obb":
        obbdir = os.path.join(ROOT, "assets", "obb")
        obb = [f for f in os.listdir(obbdir) if f.startswith("main.") and f.endswith(".obb")][0]
        with zipfile.ZipFile(os.path.join(obbdir, obb)) as z:
            return z.read("assets/setting.u")
    if source == "late":
        source = os.path.join(ROOT, "assets", "Bundles", "setting.u")
    with open(source, "rb") as f:
        return f.read()


def crlf(b):
    return b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


ITEM_COLUMNS = [  # (name, is string) in the binary order of ItemBaseInfo
    ("Genre", 0), ("Detail", 0), ("Particular", 0), ("Level", 0), ("RarityColor", 0), ("AutoUse", 0),
    ("ClassName", 1), ("DescriptionIndex", 1), ("SellingPrice", 0), ("IconId", 1), ("awardIconId", 1),
    ("ExtParam1", 1), ("ExtParam2", 1), ("ExtParam3", 1), ("ShowType", 0), ("TagIcon", 1),
    ("DisableDropWay", 0), ("LimitTime", 0), ("ExpiredDelete", 0),
]


def item_list(env):
    """ItemList.txt from the MonoBehaviour named ItemList: header (28 bytes), name, row count, rows."""
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        d = o.get_raw_data()
        n = int.from_bytes(d[28:32], "little")
        if d[32:32 + n] != b"ItemList":
            continue
        pos = 32 + (n + 3) // 4 * 4
        count = int.from_bytes(d[pos:pos + 4], "little")
        pos += 4
        tab, lf = chr(9), chr(10)  # ItemList.txt uses LF, unlike the text tables
        names = tab.join(c for c, _ in ITEM_COLUMNS)
        lines = [tab.join("STR" for _ in ITEM_COLUMNS), names, names]
        for _ in range(count):
            row = []
            for _, is_str in ITEM_COLUMNS:
                v = int.from_bytes(d[pos:pos + 4], "little", signed=True)
                pos += 4
                if is_str:
                    row.append(d[pos:pos + v].decode("utf-8"))
                    pos += (v + 3) // 4 * 4
                else:
                    row.append(str(v))
            lines.append(tab.join(row))
        return (lf.join(lines) + lf).encode("utf-8")
    sys.exit("ItemList object not found in the bundle")


def tables(raw):
    """Returns {relative file path: bytes} in the server layout."""
    env = UnityPy.load(swap(raw))
    path_of = {obj.path_id: path for path, obj in env.container.items()}
    items = []  # (container path, name, bytes) in object order
    for o in env.objects:
        if o.type.name != "TextAsset":
            continue
        a = o.read()
        s = a.m_Script
        b = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
        items.append((path_of.get(o.path_id, ""), a.m_Name, crlf(b)))
    used = collections.Counter(os.path.basename(p).lower() for p, _, _ in items if p)
    out = {}
    flat_name = {}  # lower name -> file name of the first writer
    for path, name, b in items:
        key = name.lower()
        flat_name.setdefault(key, name + ".txt")
        out[flat_name[key]] = b
        if path and used[os.path.basename(path).lower()] > 1:
            if not path.startswith(PREFIX):
                sys.exit("unexpected container path: " + path)
            out["_scoped/" + path[len(PREFIX):]] = b
    out["ItemList.txt"] = item_list(env)
    return out


def compare(out, directory):
    have = {}
    for dp, _, fs in os.walk(directory):
        for f in fs:
            rel = os.path.relpath(os.path.join(dp, f), directory).replace("\\", "/")
            have[rel.lower()] = (rel, os.path.join(dp, f))
    same = 0
    diff, new = [], []
    for rel, b in out.items():
        h = have.pop(rel.lower(), None)
        if h is None:
            new.append(rel)
        elif open(h[1], "rb").read() == b and h[0] == rel:
            same += 1
        else:
            diff.append(rel)
    print(f"same {same}, different {len(diff)}, only in bundle {len(new)}, only in directory {len(have)}")
    for label, lst in (("different", diff), ("only in bundle", new), ("only in directory", [v[0] for v in have.values()])):
        if lst:
            print(f"{label}: " + ", ".join(sorted(lst)[:40]) + (" ..." if len(lst) > 40 else ""))
    return not diff and not new


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = tables(read_source(sys.argv[1]))
    if "--compare" in sys.argv:
        ok = compare(out, sys.argv[sys.argv.index("--compare") + 1])
        sys.exit(0 if ok else 1)
    dest = sys.argv[2]
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit("output directory is not empty: " + dest)
    for rel, b in out.items():
        p = os.path.join(dest, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b)
    print(f"{len(out)} files -> {dest}")


if __name__ == "__main__":
    main()
