"""Repack the published GirlCafeGun-Remake APK with English intro art, signed with our own key.

Why an APK change: the intro (publisher splash, Seasun logo, health notice of the Chinese release) is three
textures inside assets/bin/Data/data.unity3d of the APK. A data update cannot reach them.

Cost of the route: the APK no longer has the publisher's signature. The phone needs an uninstall and a new
install once (the save goes; move files/ aside first), Play Protect asks again, and the publisher's APK
updates do not apply to this install. After that, our own APK changes install with `adb install -r`.

Stages:
  intro   Python 3.10 venv (UnityPy 1.25.2, etcpak). Writes a data.unity3d in which only the pixel bytes
          of three textures differ. Each is ETC_RGB4, 2048 x 1024, one mip, 1,048,576 bytes in a .resS
          stream, so the new pixels go over the old bytes in place. The container is unpacked and packed
          with Remake's own asset_tools (a round trip of the unchanged file gives the same data).
            bg_start_Mul      "bilibili 游戏"  -> the "bilibili" picture of the English client APK
            bg_start2_Mul     Seasun logo      -> the same picture without the characters under the word
            bg_LaunchTip_JP   health notice    -> black, with the English game logo in the middle
  axes    Python 3.10 venv. Adds the 28 raw joystick axes gcgpad_a1 .. gcgpad_a28 to the InputManager, for the
          controller layer (right stick, triggers and d-pad on any pad). Only globalgamemanagers is rewritten.
  sdk-off Python 3.10 venv. Two tracking parts off, without native code (card gcg2#27). From the APK given:
            data.unity3d  the GameObject u3dautosdk of level0 inactive (UAutoSDK, a test-automation TCP listener
                          on port 13000, never starts). One byte of the unpacked container changes.
                          Unity's own analytics off in globalgamemanagers: UnityConnectSettings.m_Enabled,
                          its UnityAnalyticsSettings.m_InitializeOnStartup and PlayerSettings.submitAnalytics
                          (cdp.cloud.unity3d.com, config.uca.cloud.unity3d.com). Three more bytes.
            classes.dex   Crasheye.init(Context, String, String) returns false at once (Crasheye, the crash and
                          session reporter, is never set up). Six bytes of code change, then the dex header
                          signature and checksum.
          Writes both files to --out-dir; the apk stage puts them in with --data and --dex.
  apk     Any Python 3.10+, a JDK, Android build-tools. Copies every entry of the APK (same compression
          method per entry), puts the new data.unity3d in, drops the old signature files, runs zipalign
          and apksigner with the PKCS12 identity in --signing-dir (the one of our update packages).
          --dex also replaces classes.dex.
          --debuggable also sets android:debuggable="true" in AndroidManifest.xml. The save is in the private
          storage of the app; with this flag `adb shell run-as <package>` can read and write it, which is what
          tools/remake/save_tool.py uses. No game code changes. Only for a phone build, never for a release.

No game asset is in this repository; all pictures come from the APK files you pass.
MIT, copyright 2026 GCG2-Offline contributors.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, zipfile
from pathlib import Path

DATA = 'assets/bin/Data/data.unity3d'
SIZE = (2048, 1024)
ETC_RGB4 = 34
sha = lambda b: hashlib.sha256(b).hexdigest()


def textures(blob, names):
    import UnityPy
    env = UnityPy.load(blob)
    found = {}
    for o in env.objects:
        if o.type.name == 'Texture2D':
            d = o.read()
            if d.m_Name in names:
                assert d.m_Name not in found, d.m_Name
                found[d.m_Name] = d
    return found


def stage_intro(a):
    from PIL import Image
    from UnityPy.export.Texture2DConverter import image_to_texture2d
    sys.path.insert(0, str(a.remake.resolve() / 'release/client'))
    import asset_tools
    import UnityPy

    raw = zipfile.ZipFile(a.apk).read(DATA)
    meta, data = asset_tools.unityfs(raw)
    assert asset_tools.unityfs(asset_tools.pack(meta, data))[1] == data, 'the container does not survive a round trip'
    nodes = {name: (offset, size) for offset, size, _, name in meta['nodes']}
    old = textures(raw, {'bg_start_Mul', 'bg_start2_Mul', 'bg_LaunchTip_JP'})
    assert len(old) == 3, sorted(old)

    # 1. the publisher splash of the English client
    en = textures(zipfile.ZipFile(a.en_apk).read(DATA), {'bg_start_Mul'})['bg_start_Mul']
    splash = en.image.convert('RGB')
    assert splash.size == SIZE
    # 2. the Seasun logo without the characters: rows 695-740, columns 911-1135 (seen in the 0.1.3 APK)
    seasun = old['bg_start2_Mul'].image.convert('RGB')
    box = (880, 680, 1170, 760)
    below = seasun.crop((box[0], box[3] + 1, box[2], box[3] + 1 + (box[3] - box[1]))).transpose(Image.FLIP_TOP_BOTTOM)
    assert max(max(p) for p in below.getdata()) < 90, 'the strip below the characters is not plain background'
    seasun.paste(below, box[:2])
    # 3. the game logo of the English client on black
    import UnityPy as _u
    atlas = _u.load(str(a.en_atlas))
    logo = [o.read() for o in atlas.objects if o.type.name == 'Sprite' and o.read().m_Name == 'login_bg_title_Mul']
    assert len(logo) == 1
    art = logo[0].image.convert('RGBA')
    art = art.resize((round(art.width * 1.25), round(art.height * 1.25)), Image.LANCZOS)
    notice = Image.new('RGB', SIZE, (0, 0, 0))
    notice.paste(art, ((SIZE[0] - art.width) // 2, (SIZE[1] - art.height) // 2), art)

    patched = bytearray(data)
    report = {'sourceApkSha256': sha(a.apk.read_bytes()), 'sourceDataSha256': sha(raw), 'textures': {}}
    ranges = []
    for name, image in (('bg_start_Mul', splash), ('bg_start2_Mul', seasun), ('bg_LaunchTip_JP', notice)):
        d = old[name]
        stream = d.m_StreamData
        assert int(d.m_TextureFormat) == ETC_RGB4 and d.m_MipCount == 1 and (d.m_Width, d.m_Height) == SIZE, name
        body, fmt = image_to_texture2d(image, ETC_RGB4)
        assert int(fmt) == ETC_RGB4 and len(body) == stream.size == d.m_CompleteImageSize, (name, len(body), stream.size)
        node = nodes[stream.path.split('/')[-1]]
        assert stream.offset + stream.size <= node[1]
        at = node[0] + stream.offset
        patched[at:at + stream.size] = body
        ranges.append((at, at + stream.size))
        report['textures'][name] = {'stream': stream.path.split('/')[-1], 'offset': stream.offset, 'bytes': stream.size}
        if a.preview_dir:
            a.preview_dir.mkdir(parents=True, exist_ok=True)
            image.save(a.preview_dir / (name + '.png'))
    # nothing else changed
    probe = bytearray(patched)
    for start, end in ranges:
        probe[start:end] = data[start:end]
    assert bytes(probe) == data
    out = asset_tools.pack(meta, bytes(patched))
    meta2, data2 = asset_tools.unityfs(out)
    assert data2 == bytes(patched) and meta2['nodes'] == meta['nodes']
    new = textures(out, set(report['textures']))
    for name, image in (('bg_start_Mul', splash), ('bg_start2_Mul', seasun), ('bg_LaunchTip_JP', notice)):
        a_, b_ = new[name].image.convert('RGB').resize((256, 128)), image.resize((256, 128))
        diff = sum(abs(x - y) for p, q in zip(a_.getdata(), b_.getdata()) for x, y in zip(p, q)) / (256 * 128 * 3)
        assert diff < 6, (name, diff)  # ETC1 is lossy; a wrong picture gives far more
        report['textures'][name]['meanDifferenceAfterEncoding'] = round(diff, 2)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(out)
    report.update(file=str(a.out), bytes=len(out), sha256=sha(out), bytesChangedOnlyInTheThreeStreams=True)
    print(json.dumps(report, indent=2))


def stage_axes(a):
    """Raw joystick axes for the controller layer: 28 InputManager entries gcgpad_a1 .. gcgpad_a28.

    The same entries as apk-build/patch_inputmanager.py makes for the C# build (docs/11-CONTROLLER.md). That tool
    saves the whole container again, which rewrites every scene file of this APK. Here only the file that holds
    the InputManager (globalgamemanagers) is written again; every other file keeps its bytes.
    """
    sys.path.insert(0, str(a.remake.resolve() / 'release/client'))
    import asset_tools
    import UnityPy

    raw = a.data.read_bytes()
    meta, data = asset_tools.unityfs(raw)
    env = UnityPy.load(raw)
    target = 'globalgamemanagers'
    managers = [o for o in env.objects if o.type.name == 'InputManager']
    assert len(managers) == 1 and managers[0].assets_file.name == target
    before = {o.path_id: o.get_raw_data() for o in env.file.files[target].objects.values()}
    tree = managers[0].read_typetree()
    axes = tree['m_Axes']
    have = {x['m_Name'] for x in axes}
    template = next(x for x in axes if x['m_Name'] == 'RightHorizontal')
    added = 0
    for i in range(1, 29):
        name = 'gcgpad_a%d' % i
        if name in have:
            continue
        row = dict(template)
        row.update(m_Name=name, descriptiveName='', descriptiveNegativeName='', negativeButton='', positiveButton='',
                   altNegativeButton='', altPositiveButton='', gravity=0.0, dead=0.0, sensitivity=1.0, snap=False,
                   invert=False, type=2, axis=i - 1, joyNum=0)
        axes.append(row)
        added += 1
    managers[0].save_typetree(tree)
    new_file = env.file.files[target].save()
    nodes, parts, at = [], [], 0
    for offset, size, flags, name in meta['nodes']:
        blob = new_file if name == target else data[offset:offset + size]
        nodes.append((at, len(blob), flags, name))
        parts.append(blob)
        at += len(blob)
    out = asset_tools.pack(dict(meta, nodes=nodes), b''.join(parts))
    meta2, data2 = asset_tools.unityfs(out)
    old = {n[3]: data[n[0]:n[0] + n[1]] for n in meta['nodes']}
    new = {n[3]: data2[n[0]:n[0] + n[1]] for n in meta2['nodes']}
    assert list(old) == list(new) and all(old[n] == new[n] for n in old if n != target)
    env2 = UnityPy.load(out)
    after = {o.path_id: o for o in env2.file.files[target].objects.values()}
    assert set(after) == set(before)
    changed = [p for p, o in after.items() if o.get_raw_data() != before[p]]
    assert changed == [managers[0].path_id], changed
    names = [x['m_Name'] for x in after[managers[0].path_id].read_typetree()['m_Axes']]
    assert all('gcgpad_a%d' % i in names for i in range(1, 29))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(out)
    print(json.dumps({'file': str(a.out), 'bytes': len(out), 'sha256': sha(out), 'axesAdded': added, 'axesTotal': len(names),
                      'onlyFileRewritten': target, 'onlyObjectChanged': 'InputManager',
                      'fileBytes': [len(old[target]), len(new[target])]}, indent=2))


DEX = 'classes.dex'
# The test-automation listener: UAutoSDK.UAutoSdkInit on this GameObject opens TCP port 13000 in Awake.
SDK_OFF_SCENE, SDK_OFF_OBJECT = 'level0', 'u3dautosdk'
# Crasheye's real init: the public init* entry points all call it; with false nothing is set up or sent.
CRASHEYE = ('Lcom/xsj/crasheye/Crasheye;', 'init', '(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;)Z')
# Its first two instructions are const/4 v6, 0 and if-nez v4, +8. The second becomes return v6 and a nop: the method
# returns false before it reads anything. The instructions after it stay as they are (unreachable).
CRASHEYE_OLD = (0x0612, 0x0439, 0x0008)
CRASHEYE_NEW = (0x0612, 0x060F, 0x0000)


def _uleb(b, at):
    value = shift = 0
    while True:
        byte = b[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, at
        shift += 7


def dex_method_code(dex, cls, name, signature):
    """Offset of the code_item of one method, found through the dex tables (header, ids, class data)."""
    import struct
    u16 = lambda o: struct.unpack_from('<H', dex, o)[0]
    u32 = lambda o: struct.unpack_from('<I', dex, o)[0]
    assert dex[:4] == b'dex\n' and u32(32) == len(dex), 'not a whole dex file'
    strings_at, types_at, protos_at = u32(60), u32(68), u32(76)
    methods_n, methods_at, classes_n, classes_at = u32(88), u32(92), u32(96), u32(100)

    def string(i):
        _, at = _uleb(dex, u32(strings_at + 4 * i))
        return dex[at:dex.index(b'\0', at)].decode('utf8')

    def type_name(i):
        return string(u32(types_at + 4 * i))

    def proto(i):
        at = protos_at + 12 * i
        params_at, params = u32(at + 8), []
        if params_at:
            params = [type_name(u16(params_at + 4 + 2 * k)) for k in range(u32(params_at))]
        return '(' + ''.join(params) + ')' + type_name(u32(at + 4))

    wanted = [m for m in range(methods_n)
              if type_name(u16(methods_at + 8 * m)) == cls and string(u32(methods_at + 8 * m + 4)) == name
              and proto(u16(methods_at + 8 * m + 2)) == signature]
    assert len(wanted) == 1, ('method id', cls, name, signature, wanted)
    found = []
    for c in range(classes_n):
        at = classes_at + 32 * c
        if type_name(u32(at)) != cls or not u32(at + 24):
            continue
        p = u32(at + 24)
        sizes = []
        for _ in range(4):
            v, p = _uleb(dex, p)
            sizes.append(v)
        for _ in range(sizes[0] + sizes[1]):
            _, p = _uleb(dex, p)
            _, p = _uleb(dex, p)
        for count in sizes[2:]:
            index = 0
            for _ in range(count):
                diff, p = _uleb(dex, p)
                _, p = _uleb(dex, p)
                code, p = _uleb(dex, p)
                index += diff
                if index == wanted[0]:
                    found.append(code)
    assert len(found) == 1 and found[0], ('code item', found)
    return found[0]


def dex_with_header(dex):
    """The dex with its SHA-1 signature and Adler-32 checksum computed again."""
    import hashlib, zlib
    out = bytearray(dex)
    out[12:32] = hashlib.sha1(bytes(out[32:])).digest()
    out[8:12] = (zlib.adler32(bytes(out[12:])) & 0xFFFFFFFF).to_bytes(4, 'little')
    return bytes(out)


def crasheye_off(dex):
    """classes.dex with Crasheye.init(Context, String, String) returning false at once. Returns (dex, proof)."""
    import struct
    code = dex_method_code(dex, *CRASHEYE)
    registers, ins, _outs, _tries, _debug, size = struct.unpack_from('<4HII', dex, code)
    assert ins == 3 and registers == 7 and size > len(CRASHEYE_OLD), (registers, ins, size)
    insns = code + 16
    now = struct.unpack_from('<3H', dex, insns)
    if now == CRASHEYE_NEW:
        return dex, {'codeItem': code, 'alreadyPatched': True}
    assert now == CRASHEYE_OLD, ('Crasheye.init does not start as expected', [hex(x) for x in now])
    out = bytearray(dex)
    struct.pack_into('<3H', out, insns, *CRASHEYE_NEW)
    out = dex_with_header(out)
    changed = [i for i in range(len(dex)) if dex[i] != out[i]]
    assert all(i < 32 or insns <= i < insns + 6 for i in changed), changed
    assert struct.unpack_from('<3H', out, insns) == CRASHEYE_NEW and dex_with_header(out) == out
    return out, {'codeItem': code, 'insnsOffset': insns, 'codeUnitsBefore': [hex(x) for x in CRASHEYE_OLD],
                 'codeUnitsAfter': [hex(x) for x in CRASHEYE_NEW], 'bytesChangedOutsideHeader': sum(i >= 32 for i in changed)}


def uauto_off(raw, asset_tools, UnityPy):
    """data.unity3d with the GameObject u3dautosdk of level0 inactive. Returns (data.unity3d, proof).

    Disabling only the component is not enough: Unity calls Awake on a disabled component of an active object.
    m_IsActive is the last field of a GameObject, so one byte of the unpacked container changes.
    """
    meta, data = asset_tools.unityfs(raw)
    nodes = {name: (offset, size) for offset, size, _, name in meta['nodes']}
    env = UnityPy.load(raw)
    scene = env.file.files[SDK_OFF_SCENE]
    objects = [o for o in scene.objects.values() if o.type.name == 'GameObject' and o.read().m_Name == SDK_OFF_OBJECT]
    assert len(objects) == 1, len(objects)
    obj = objects[0]
    tree = obj.read_typetree()
    assert list(tree)[-1] == 'm_IsActive', list(tree)
    body = obj.get_raw_data()
    if not tree['m_IsActive']:
        return raw, {'alreadyInactive': True}
    assert body[-1] == 1, body[-1:]
    start = nodes[SDK_OFF_SCENE][0] + obj.byte_start
    assert data[start:start + len(body)] == body, 'object bytes not found where the file says'
    at = start + len(body) - 1
    patched = bytearray(data)
    patched[at] = 0
    out = asset_tools.pack(meta, bytes(patched))
    meta2, data2 = asset_tools.unityfs(out)
    assert data2 == bytes(patched) and meta2['nodes'] == meta['nodes']
    # read back: the object is inactive, every other object of every file keeps its bytes
    before = {(f, p): o.get_raw_data() for f, sf in env.file.files.items() if hasattr(sf, 'objects') for p, o in sf.objects.items()}
    env2 = UnityPy.load(out)
    after = {(f, p): o.get_raw_data() for f, sf in env2.file.files.items() if hasattr(sf, 'objects') for p, o in sf.objects.items()}
    assert set(before) == set(after)
    changed = [k for k in before if before[k] != after[k]]
    assert changed == [(SDK_OFF_SCENE, obj.path_id)], changed
    assert env2.file.files[SDK_OFF_SCENE].objects[obj.path_id].read_typetree()['m_IsActive'] is False
    return out, {'file': SDK_OFF_SCENE, 'gameObject': SDK_OFF_OBJECT, 'pathId': obj.path_id, 'byteOffset': at,
                 'onlyObjectChanged': True}


# Unity's own analytics (phone capture 2026-11-16, APK gcg2-d: HTTPS to cdp.cloud.unity3d.com and
# config.uca.cloud.unity3d.com, the URLs of UnityConnectSettings). Each switch is one boolean byte in globalgamemanagers.
ANALYTICS_FILE = 'globalgamemanagers'
ANALYTICS_OFF = {
    'UnityConnectSettings': [('m_Enabled',), ('UnityAnalyticsSettings', 'm_InitializeOnStartup')],
    'PlayerSettings': [('submitAnalytics',)],
}
# Switches that must already be off (the stage checks them and leaves them as they are).
ANALYTICS_ALREADY_OFF = {
    'UnityConnectSettings': [('CrashReportingSettings', 'm_Enabled'), ('UnityAnalyticsSettings', 'm_Enabled'),
                             ('PerformanceReportingSettings', 'm_Enabled'), ('UnityAdsSettings', 'm_Enabled'),
                             ('UnityPurchasingSettings', 'm_Enabled')],
    'PlayerSettings': [('cloudEnabled',)],
}


def _get(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def _set(tree, path, value):
    for key in path[:-1]:
        tree = tree[key]
    tree[path[-1]] = value


def analytics_off(raw, asset_tools, UnityPy):
    """data.unity3d with Unity's analytics switches of ANALYTICS_OFF set to false. Returns (data.unity3d, proof).

    Each switch is one byte of globalgamemanagers; the bytes are written in place, nothing else moves.
    """
    meta, data = asset_tools.unityfs(raw)
    nodes = {name: (offset, size) for offset, size, _, name in meta['nodes']}
    env = UnityPy.load(raw)
    managers = env.file.files[ANALYTICS_FILE]
    by_type = {}
    for o in managers.objects.values():
        by_type.setdefault(o.type.name, []).append(o)
    to_flip, proof = 0, {'set': {}, 'alreadyOff': {}}
    for type_name, paths in ANALYTICS_OFF.items():
        assert len(by_type.get(type_name, [])) == 1, type_name
        obj = by_type[type_name][0]
        tree = obj.read_typetree()
        for path in ANALYTICS_ALREADY_OFF.get(type_name, []):
            assert _get(tree, path) is False, (type_name, path)
            proof['alreadyOff']['.'.join((type_name,) + path)] = False
        changed = False
        for path in paths:
            name = '.'.join((type_name,) + path)
            if _get(tree, path) is False:
                proof['set'][name] = 'already false'
                continue
            assert _get(tree, path) is True, name
            _set(tree, path, False)
            proof['set'][name] = 'true -> false'
            changed, to_flip = True, to_flip + 1
        if changed:
            obj.save_typetree(tree)
    if not to_flip:
        return raw, dict(proof, bytesChanged=0)
    start, size = nodes[ANALYTICS_FILE]
    old = data[start:start + size]
    new = managers.save()
    assert len(new) == len(old), 'globalgamemanagers changed its size'
    positions = [i for i in range(len(old)) if old[i] != new[i]]
    assert len(positions) == to_flip and all(old[i] == 1 and new[i] == 0 for i in positions), positions
    patched = bytearray(data)
    for i in positions:
        patched[start + i] = 0
    out = asset_tools.pack(meta, bytes(patched))
    meta2, data2 = asset_tools.unityfs(out)
    assert data2 == bytes(patched) and meta2['nodes'] == meta['nodes']
    # read back: the switches are off, and only the objects that hold them changed
    env2 = UnityPy.load(out)
    before = {(f, p): o.get_raw_data() for f, sf in UnityPy.load(raw).file.files.items() if hasattr(sf, 'objects')
              for p, o in sf.objects.items()}
    after = {(f, p): o for f, sf in env2.file.files.items() if hasattr(sf, 'objects') for p, o in sf.objects.items()}
    assert set(before) == set(after)
    changed = sorted(k for k in before if before[k] != after[k].get_raw_data())
    assert changed == sorted((ANALYTICS_FILE, by_type[t][0].path_id) for t in ANALYTICS_OFF
                             if any(proof['set']['.'.join((t,) + p)] == 'true -> false' for p in ANALYTICS_OFF[t])), changed
    for type_name, paths in ANALYTICS_OFF.items():
        tree = after[(ANALYTICS_FILE, by_type[type_name][0].path_id)].read_typetree()
        assert all(_get(tree, p) is False for p in paths + ANALYTICS_ALREADY_OFF.get(type_name, [])), type_name
    return out, dict(proof, bytesChanged=len(positions), byteOffsets=[start + i for i in positions])


def stage_sdk_off(a):
    """UAutoSDK listener, Unity analytics and Crasheye off: writes <out-dir>/data.unity3d and <out-dir>/classes.dex."""
    sys.path.insert(0, str(a.remake.resolve() / 'release/client'))
    import asset_tools
    import UnityPy
    with zipfile.ZipFile(a.apk) as z:
        raw, dex = z.read(DATA), z.read(DEX)
    data, scene_proof = uauto_off(raw, asset_tools, UnityPy)
    data, analytics_proof = analytics_off(data, asset_tools, UnityPy)
    new_dex, dex_proof = crasheye_off(dex)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / 'data.unity3d').write_bytes(data)
    (a.out_dir / DEX).write_bytes(new_dex)
    print(json.dumps({'sourceApkSha256': sha(a.apk.read_bytes()), 'uauto': scene_proof, 'unityAnalytics': analytics_proof, 'crasheye': dex_proof,
                      'data': {'file': str(a.out_dir / 'data.unity3d'), 'sha256': sha(data)},
                      'dex': {'file': str(a.out_dir / DEX), 'sha256': sha(new_dex)}}, indent=2))


MANIFEST = 'AndroidManifest.xml'
ATTR_DEBUGGABLE = 0x0101000f


def debuggable_manifest(axml):
    """Return the binary AndroidManifest.xml with android:debuggable set to true on <application>.

    The manifest of the Remake APK already holds the attribute with the value false, so four bytes change:
    the data of that one typed value. The file keeps its size.
    """
    import struct
    u16 = lambda o: struct.unpack_from('<H', axml, o)[0]
    u32 = lambda o: struct.unpack_from('<I', axml, o)[0]
    assert u16(0) == 0x0003 and u32(4) == len(axml), 'not a binary XML file'
    sp = u16(2)
    assert u16(sp) == 0x0001, 'no string pool'
    sp_size = u32(sp + 4)
    rm = sp + sp_size
    assert u16(rm) == 0x0180, 'no resource map'
    ids = [u32(rm + 8 + 4 * i) for i in range((u32(rm + 4) - 8) // 4)]
    name = ids.index(ATTR_DEBUGGABLE)  # an attribute name has the index of its id in the resource map
    out = bytearray(axml)
    at, hits, depth_of_app = rm + u32(rm + 4), [], None
    path = []
    while at < len(axml):
        kind, size = u16(at), u32(at + 4)
        if kind == 0x0102:
            path.append(u32(at + 20))
            start, each, n = struct.unpack_from('<3H', axml, at + 24)
            assert each == 20
            for i in range(n):
                row = at + 16 + start + 20 * i
                if u32(row + 4) == name:
                    kind_of_value, value = axml[row + 15], u32(row + 16)
                    assert len(path) == 2 and kind_of_value == 0x12 and value == 0, (path, kind_of_value, value)
                    struct.pack_into('<I', out, row + 16, 0xFFFFFFFF)  # boolean true
                    hits.append(row + 16)
        elif kind == 0x0103:
            path.pop()
        at += size
    assert at == len(axml) and len(hits) == 1, hits
    return bytes(out), {'offset': hits[0], 'bytesChanged': sum(x != y for x, y in zip(axml, out)), 'bytes': len(out)}


def stage_apk(a):
    new_data = a.data.read_bytes()
    replaced = {DATA: new_data}
    if getattr(a, 'dex', None):
        replaced[DEX] = a.dex.read_bytes()
    manifest_proof = None
    if a.debuggable:
        with zipfile.ZipFile(a.apk) as src:
            replaced[MANIFEST], manifest_proof = debuggable_manifest(src.read(MANIFEST))
    unsigned = a.out.with_suffix('.unsigned.apk')
    aligned = a.out.with_suffix('.aligned.apk')
    signed = a.out.with_suffix('.signed.apk')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    bt = Path(a.build_tools)
    env = dict(os.environ, JAVA_HOME=str(Path(a.java_home)), PATH=str(Path(a.java_home) / 'bin') + os.pathsep + os.environ['PATH'])

    def run(args):
        r = subprocess.run([str(x) for x in args], capture_output=True, text=True, env=env)
        if r.returncode:
            sys.exit('failed: %s\n%s\n%s' % (args[0], r.stdout, r.stderr))
        return r.stdout

    # The temporary files are full-size APKs: they go also when a step fails (wrong keystore password, missing
    # tool). apksigner writes to a temporary name; --out is replaced only by an APK that passed verify, so a
    # failed run keeps an earlier output and never leaves a half-signed one.
    dropped, copied = [], 0
    try:
        with zipfile.ZipFile(a.apk) as src, zipfile.ZipFile(unsigned, 'w', allowZip64=False) as dst:
            for info in src.infolist():
                name = info.filename
                if name.startswith('META-INF/') and name.rsplit('.', 1)[-1].upper() in ('SF', 'RSA', 'DSA', 'EC', 'MF'):
                    dropped.append(name)
                    continue
                body = replaced[name] if name in replaced else src.read(info)
                row = zipfile.ZipInfo(name, info.date_time)
                row.compress_type = info.compress_type
                row.external_attr = info.external_attr
                row.create_system = info.create_system
                dst.writestr(row, body, compress_type=info.compress_type, compresslevel=6)
                copied += 1
        run([bt / 'zipalign.exe', '-f', '-p', '4', unsigned, aligned])
        signing = Path(a.signing_dir)
        password = 'file:' + str(signing / 'password.txt')
        run([bt / 'apksigner.bat', 'sign', '--ks', signing / 'release.p12', '--ks-type', 'PKCS12', '--ks-key-alias', 'gcg-release',
             '--ks-pass', password, '--out', signed, aligned])  # the key uses the keystore password
        certs = run([bt / 'apksigner.bat', 'verify', '--print-certs', signed])
        os.replace(signed, a.out)
    finally:
        for temp in (unsigned, aligned, signed, Path(str(signed) + '.idsig')):
            if temp.exists():
                temp.unlink()
    with zipfile.ZipFile(a.apk) as src, zipfile.ZipFile(a.out) as dst:
        before = {i.filename: i.CRC for i in src.infolist() if i.filename not in dropped}
        after = {i.filename: i.CRC for i in dst.infolist() if not i.filename.startswith('META-INF/')}
        changed = sorted(n for n in before if not n.startswith('META-INF/') and before[n] != after.get(n))
        assert changed == sorted(replaced), changed
        assert set(after) == {n for n in before if not n.startswith('META-INF/')}
        assert all(dst.read(n) == b for n, b in replaced.items())
    print(json.dumps({'file': str(a.out), 'bytes': a.out.stat().st_size, 'sha256': sha(a.out.read_bytes()),
                      'entriesCopied': copied, 'signatureFilesDropped': dropped, 'onlyChangedEntries': sorted(replaced),
                      'debuggable': manifest_proof,
                      'signer': [l.strip() for l in certs.splitlines() if 'certificate DN' in l or 'SHA-256' in l]}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='stage', required=True)
    s = sub.add_parser('intro')
    s.add_argument('--apk', type=Path, required=True, help='published Remake APK')
    s.add_argument('--en-apk', type=Path, required=True, help='English client APK (for its bg_start_Mul)')
    s.add_argument('--en-atlas', type=Path, required=True, help='ui_tx/ui_login.u of the English client data (for the game logo)')
    s.add_argument('--remake', type=Path, required=True, help='Remake checkout (release/client/asset_tools.py)')
    s.add_argument('--out', type=Path, required=True); s.add_argument('--preview-dir', type=Path)
    s.set_defaults(run=stage_intro)
    s = sub.add_parser('axes')
    s.add_argument('--data', type=Path, required=True, help='data.unity3d (the output of the intro stage)')
    s.add_argument('--remake', type=Path, required=True); s.add_argument('--out', type=Path, required=True)
    s.set_defaults(run=stage_axes)
    s = sub.add_parser('sdk-off')
    s.add_argument('--apk', type=Path, required=True, help='the APK to start from (for example our earlier repack)')
    s.add_argument('--remake', type=Path, required=True); s.add_argument('--out-dir', type=Path, required=True)
    s.set_defaults(run=stage_sdk_off)
    s = sub.add_parser('apk')
    s.add_argument('--apk', type=Path, required=True); s.add_argument('--data', type=Path, required=True)
    s.add_argument('--signing-dir', type=Path, required=True); s.add_argument('--build-tools', required=True)
    s.add_argument('--java-home', required=True); s.add_argument('--out', type=Path, required=True)
    s.add_argument('--dex', type=Path, help='classes.dex to put in (the output of the sdk-off stage)')
    s.add_argument('--debuggable', action='store_true',
                   help='set android:debuggable on <application>, so that adb run-as reaches the save (tools/remake/save_tool.py)')
    s.set_defaults(run=stage_apk)
    a = p.parse_args()
    a.run(a)


if __name__ == '__main__':
    main()
