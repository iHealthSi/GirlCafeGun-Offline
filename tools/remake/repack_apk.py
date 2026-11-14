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
  apk     Any Python 3.10+, a JDK, Android build-tools. Copies every entry of the APK (same compression
          method per entry), puts the new data.unity3d in, drops the old signature files, runs zipalign
          and apksigner with the PKCS12 identity in --signing-dir (the one of our update packages).

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
    a.out.write_bytes(out)
    print(json.dumps({'file': str(a.out), 'bytes': len(out), 'sha256': sha(out), 'axesAdded': added, 'axesTotal': len(names),
                      'onlyFileRewritten': target, 'onlyObjectChanged': 'InputManager',
                      'fileBytes': [len(old[target]), len(new[target])]}, indent=2))


def stage_apk(a):
    new_data = a.data.read_bytes()
    unsigned = a.out.with_suffix('.unsigned.apk')
    aligned = a.out.with_suffix('.aligned.apk')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    dropped, copied = [], 0
    with zipfile.ZipFile(a.apk) as src, zipfile.ZipFile(unsigned, 'w', allowZip64=False) as dst:
        for info in src.infolist():
            name = info.filename
            if name.startswith('META-INF/') and name.rsplit('.', 1)[-1].upper() in ('SF', 'RSA', 'DSA', 'EC', 'MF'):
                dropped.append(name)
                continue
            body = new_data if name == DATA else src.read(info)
            row = zipfile.ZipInfo(name, info.date_time)
            row.compress_type = info.compress_type
            row.external_attr = info.external_attr
            row.create_system = info.create_system
            dst.writestr(row, body, compress_type=info.compress_type, compresslevel=6)
            copied += 1
    bt = Path(a.build_tools)
    env = dict(os.environ, JAVA_HOME=str(Path(a.java_home)), PATH=str(Path(a.java_home) / 'bin') + os.pathsep + os.environ['PATH'])

    def run(args):
        r = subprocess.run([str(x) for x in args], capture_output=True, text=True, env=env)
        if r.returncode:
            sys.exit('failed: %s\n%s\n%s' % (args[0], r.stdout, r.stderr))
        return r.stdout

    run([bt / 'zipalign.exe', '-f', '-p', '4', unsigned, aligned])
    signing = Path(a.signing_dir)
    password = 'file:' + str(signing / 'password.txt')
    run([bt / 'apksigner.bat', 'sign', '--ks', signing / 'release.p12', '--ks-type', 'PKCS12', '--ks-key-alias', 'gcg-release',
         '--ks-pass', password, '--out', a.out, aligned])  # the key uses the keystore password
    certs = run([bt / 'apksigner.bat', 'verify', '--print-certs', a.out])
    unsigned.unlink(); aligned.unlink()
    idsig = Path(str(a.out) + '.idsig')
    if idsig.exists():
        idsig.unlink()
    with zipfile.ZipFile(a.apk) as src, zipfile.ZipFile(a.out) as dst:
        before = {i.filename: i.CRC for i in src.infolist() if i.filename not in dropped}
        after = {i.filename: i.CRC for i in dst.infolist() if not i.filename.startswith('META-INF/')}
        changed = sorted(n for n in before if not n.startswith('META-INF/') and before[n] != after.get(n))
        assert changed == [DATA], changed
        assert set(after) == {n for n in before if not n.startswith('META-INF/')}
        assert dst.read(DATA) == new_data
    print(json.dumps({'file': str(a.out), 'bytes': a.out.stat().st_size, 'sha256': sha(a.out.read_bytes()),
                      'entriesCopied': copied, 'signatureFilesDropped': dropped, 'onlyChangedEntry': DATA,
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
    s = sub.add_parser('apk')
    s.add_argument('--apk', type=Path, required=True); s.add_argument('--data', type=Path, required=True)
    s.add_argument('--signing-dir', type=Path, required=True); s.add_argument('--build-tools', required=True)
    s.add_argument('--java-home', required=True); s.add_argument('--out', type=Path, required=True)
    s.set_defaults(run=stage_apk)
    a = p.parse_args()
    a.run(a)


if __name__ == '__main__':
    main()
