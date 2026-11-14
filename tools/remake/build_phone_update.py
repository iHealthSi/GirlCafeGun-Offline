"""Build our update package for a phone that runs the published GirlCafeGun-Remake release.

The phone keeps the official Remake APK (signed by its publisher). Our changes go on top as a
locally signed `.gcgupdate` (Remake docs/update-format.md, "Locally signed user-created data
updates"): a patched `lua.u`, the matching `version.data` and a server payload.

Stages (run each with the Python that the stage names):
  lua     Python 3.10 venv with release/client/requirements.txt (UnityPy 1.25.2, lupa).
          --hooks-only (the way that works): patches assets/lua.u of the release APK with the
          controller and title recipes of <client-dir> and nothing else.
          Without it: runs the whole patch_lua.py on assets/lua.u.orig; with --expect-release the
          result must equal assets/lua.u. On the 0.1.3 APK this stops in patch_selectors, because
          lua.u.orig is not the input that Remake's build pins.
  art     Python 3.10 venv. Paints the English logo, "Tap Screen to Start" and "Log Out" from the English
          client's ui_tx/ui_login.u into the same atlas of the installed Remake data. Pixels only.
  server  Any Python 3.10+, Node.js 22+. Compiles <server-dir>/src with tsc and puts the result
          in place of dist/ inside the payload of the release APK. Everything else in the payload
          (bootstrap, config, tables, zod) stays byte for byte. With --compare-only it reports
          the modules that differ from the release payload and writes nothing.
  pack    Python 3.10 venv, a JDK. Reconciles version.data (the copy pulled from the phone), then calls
          Remake's own release/tools/make_update.py in-process with the signing identity moved to
          --signing-dir, so no tracked file of the Remake checkout changes. It writes
          manifest-<release id>.json next to the package: the full file list of the new release.
          The next update needs it as --base-manifest, because the installed release id is then ours.

Nothing here downloads anything or talks to the phone. MIT, copyright 2026 GCG2-Offline contributors.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, secrets, shutil, subprocess, sys, zipfile
from pathlib import Path

sha = lambda b: hashlib.sha256(b).hexdigest()


def apk_read(apk, name):
    with zipfile.ZipFile(apk) as z:
        return z.read(name)


def norm_js(body):
    return '\n'.join(l for l in body.decode('utf8').replace('\r\n', '\n').splitlines()
                     if not l.startswith('//# sourceMappingURL=')).strip()


# Remake's client is the Chinese package: Game.Localization.Lang is zh_CN and the text table is English.
# So the login screen shows two things that only the Chinese release has: the age rating badge
# (BtnAgeLimit) and the health notice with the licence line (TipCN). The English client hides both.
CN_ONLY = (
    ('\t\tself.btnAgeLimit.gameObject:SetActive(Game.Localization.Lang == Game.LangType.zh_CN);\n',
     '\t\tself.btnAgeLimit.gameObject:SetActive(false);\n'),
    ('\tobjTipCN:SetActive(Game.Localization.Lang == Game.LangType.zh_CN);\n',
     '\tobjTipCN:SetActive(false);\n'),
)


def english_title_script(name, source):
    text = source.decode('utf8').replace('\r\n', '\n')
    for old, new in CN_ONLY:
        if text.count(new) == 1 and old not in text:
            continue  # already patched
        assert text.count(old) == 1 and new not in text, old
        text = text.replace(old, new)
    return text.encode('utf8')


def stage_art(a):
    """Paint the English versions of some login sprites into Remake's own sprite atlas.

    Both data sets hold ui_tx/ui_login.u: the atlas UI_Login with the same 27 sprites and the same keys.
    Remake's holds the Chinese logo, ours (EN build 179) the English one. Only pixels change here: every
    rectangle, key and object of Remake's bundle stays, so the login prefab binds to it as before. The
    texture is written as RGBA32, so the sprites that are not touched keep their decoded pixels exactly.
    """
    import UnityPy
    from PIL import Image
    from UnityPy.enums import TextureFormat

    def plain(key):
        guid, file_id = key
        return tuple(getattr(guid, 'data_%d_' % i) for i in range(4)), file_id

    def load(path):
        env = UnityPy.load(str(path))
        atlas = [o.read() for o in env.objects if o.type.name == 'SpriteAtlas']
        tex = [o.read() for o in env.objects if o.type.name == 'Texture2D']
        assert len(atlas) == 1 and len(tex) == 1, (path, len(atlas), len(tex))
        sprites = {}
        for o in env.objects:
            if o.type.name == 'Sprite':
                d = o.read()
                assert d.m_Name not in sprites
                sprites[d.m_Name] = d
        m = atlas[0].m_RenderDataMap
        rects = {plain(key): value.textureRect for key, value in (m.items() if hasattr(m, 'items') else m)}
        return env, atlas[0], tex[0], sprites, rects

    def flat(rects):
        return {k: (v.x, v.y, v.width, v.height) for k, v in rects.items()}

    env, atlas, tex, sprites, rects = load(a.remake_atlas)
    _, en_atlas, _, en_sprites, _ = load(a.en_atlas)
    assert atlas.m_Name == en_atlas.m_Name == 'UI_Login' and set(sprites) == set(en_sprites)
    assert {n: plain(s.m_RenderDataKey) for n, s in sprites.items()} == {n: plain(s.m_RenderDataKey) for n, s in en_sprites.items()}
    base = tex.image.convert('RGBA')
    before = base.copy()
    width, height = base.size
    report = {'texture': tex.m_Name, 'size': [width, height], 'painted': {}}
    boxes = []
    for name in a.names:
        r = rects[plain(sprites[name].m_RenderDataKey)]
        x, y, w, h = round(r.x), round(r.y), round(r.width), round(r.height)
        top = height - (y + h)  # Unity counts rows from the bottom
        art = en_sprites[name].image.convert('RGBA')
        scale = min(w / art.width, h / art.height, 1.0)
        size = (max(1, round(art.width * scale)), max(1, round(art.height * scale)))
        if size != art.size:
            art = art.resize(size, Image.LANCZOS)
        base.paste(Image.new('RGBA', (w, h), (0, 0, 0, 0)), (x, top))
        base.paste(art, (x + (w - size[0]) // 2, top + (h - size[1]) // 2))
        boxes.append((x, top, x + w, top + h))
        report['painted'][name] = {'box': [x, top, w, h], 'english': list(en_sprites[name].image.size), 'drawn': list(size)}
    probe = base.copy()
    for box in boxes:
        probe.paste(before.crop(box), box[:2])
    assert probe.tobytes() == before.tobytes(), 'a pixel outside the painted rectangles changed'
    tex.set_image(base, target_format=TextureFormat.RGBA32)
    tex.save()
    blob = env.file.save(packer='lz4')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(blob)
    _, _, tex2, sprites2, rects2 = load(a.out)
    assert set(sprites2) == set(sprites) and flat(rects2) == flat(rects)
    assert tex2.image.convert('RGBA').tobytes() == base.tobytes(), 'the texture does not read back'
    if a.preview:
        base.save(a.preview)
    report.update(file=str(a.out), bytes=len(blob), sha256=sha(blob), sourceSha256=sha(a.remake_atlas.read_bytes()),
                  englishSha256=sha(a.en_atlas.read_bytes()), readsBack=True)
    print(json.dumps(report, indent=2))


def stage_lua(a):
    sys.path.insert(0, str(a.client_dir.resolve()))
    import patch_lua
    if a.hooks_only:
        # The release APK does not hold the input that Remake's build pins (its lua.u.orig is an earlier
        # stage: patch_selectors stops on it). So start from the released lua.u and run only the two
        # recipes that the release does not have. Both run last in patch_script, on its result, so the
        # scripts they get here are the scripts they get in a full build.
        import patch_gamepad, patch_title
        hooks = {n: [m.lua_script] for m in (patch_gamepad, patch_title) for n in m.LUA_NAMES}
        if a.english_title:
            hooks.setdefault('UI_Login.lua', []).append(english_title_script)
        patch_lua.NAMES = set(hooks)

        def patch_script(name, data):
            for hook in hooks[name]:
                data = hook(name, data)
            return data
        patch_lua.patch_script = patch_script
        source = apk_read(a.apk, 'assets/lua.u')
    else:
        source = apk_read(a.apk, 'assets/lua.u.orig')
    built, proof = patch_lua.build(source)
    out = {'clientDir': str(a.client_dir), 'sourceSha256': sha(source), 'builtSha256': sha(built), 'bytes': len(built),
           'changedScripts': sorted(proof['changedScripts'])}
    if a.expect_release:
        release = apk_read(a.apk, 'assets/lua.u')
        out['releaseSha256'] = sha(release)
        out['reproducesRelease'] = built == release
    if a.tests:
        import test_gamepad, test_title
        out['gamepadBehavior'] = bool(test_gamepad.run_bundle(built))
        out['titleBehavior'] = bool(test_title.run_bundle(built))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_bytes(built)
        out['file'] = str(a.out)
    print(json.dumps(out, indent=2))
    if a.expect_release and not out['reproducesRelease']:
        sys.exit(2)


def stage_server(a):
    server = a.server_dir.resolve()
    link = server / 'node_modules'
    made_link = False
    if not link.exists():
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(a.node_modules.resolve())], check=True, capture_output=True)
        made_link = True
    compiled = a.work.resolve() / 'compiled'
    if compiled.exists():
        shutil.rmtree(compiled)
    try:
        subprocess.run([shutil.which('node'), str(a.node_modules.resolve() / 'typescript/bin/tsc'), '-p', 'tsconfig.build.json',
                        '--outDir', str(compiled), '--declaration', 'false', '--declarationMap', 'false', '--sourceMap', 'false'],
                       cwd=server, check=True)
    finally:
        if made_link:
            os.rmdir(link)  # removes the junction only, never its target
    runtime = {'dist/' + p.relative_to(compiled).as_posix(): p.read_bytes() for p in sorted(compiled.rglob('*.js'))
               if p.relative_to(compiled).parts[0] != 'tools'}
    sources = {'dist/' + p.relative_to(server / 'src').as_posix()[:-3] + '.js' for p in (server / 'src').rglob('*.ts')
               if p.relative_to(server / 'src').parts[0] != 'tools'}
    assert set(runtime) == sources, sorted(set(runtime) ^ sources)[:10]
    with zipfile.ZipFile(io.BytesIO(apk_read(a.apk, 'assets/gcg-server/payload.zip'))) as z:
        base = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    base_dist = {n for n in base if n.startswith('dist/')}
    changed = sorted(n for n in base_dist & set(runtime) if norm_js(base[n]) != norm_js(runtime[n]))
    report = {'serverDir': str(server), 'baselinePayloadSha256': sha(apk_read(a.apk, 'assets/gcg-server/payload.zip')),
              'runtimeModules': len(runtime), 'changedModules': changed,
              'addedModules': sorted(set(runtime) - base_dist), 'removedModules': sorted(base_dist - set(runtime))}
    if not a.compare_only:
        members = {n: b for n, b in base.items() if not n.startswith('dist/')}
        members.update(runtime)
        assert all(not n.startswith(('data/', 'logs/', 'test/', 'src/', 'dist/tools/')) for n in members)
        assert not any('profile' in n.lower() or 'state.json' in n.lower() for n in members)
        assert 'ensureNeptuneTrialRoster' not in members['dist/persistence/player-repository.js'].decode('utf8')
        sys.path.insert(0, str(a.remake.resolve() / 'release/tools'))
        import payload_codec
        blob = payload_codec.archive(members)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        payload_codec.write_verified(a.out, blob)
        report.update(file=str(a.out), sha256=sha(blob), bytes=len(blob), entries=len(members),
                      keptFromRelease=len(members) - len(runtime))
    print(json.dumps(report, indent=2))


def stage_pack(a):
    remake = a.remake.resolve()
    work = a.work.resolve()
    changes = work / 'changes'
    if changes.exists():
        shutil.rmtree(changes)
    changes.mkdir(parents=True)
    shutil.copyfile(a.lua, changes / 'lua.u')
    if a.extra:
        for p in sorted(a.extra.rglob('*')):
            if p.is_file():
                target = changes / p.relative_to(a.extra)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
    # The base is the release that is installed now: the APK's manifest, or the full manifest that an
    # earlier run of this stage wrote for our own release (--base-manifest).
    base_bytes = a.base_manifest.read_bytes() if a.base_manifest else apk_read(a.apk, 'assets/gcg-release/manifest.json')
    manifest = json.loads(base_bytes)
    rows = {r['path']: r for r in manifest['files']}
    index = a.version_data.read_bytes()
    sys.path.insert(0, str(remake / 'release/client'))
    import patch_index
    from version_manifest import Manifest
    # The game rewrites files/version.data at its first start (the asset routes change, the bundle records
    # do not), so the phone's copy does not have the hash of the release manifest. Build on the phone's
    # copy, and check that it describes the installed release: every changed bundle has the released size.
    records = {r.name: r for r in Manifest(index).records}
    paired = {p.relative_to(changes).as_posix(): p for p in sorted(changes.rglob('*')) if p.is_file()}
    for name in paired:
        if name in rows:
            assert name in records, name + ' has no record in the index'
            assert records[name].size == rows[name]['size'], name + ': the index is not the one of the installed release'
        else:
            assert name.endswith('.u'), name + ': only bundles can be added'
    # A bundle that the installed release does not hold is an addition. The index gets its size and CRC only
    # when it already names the bundle; a bundle the index does not name is on disk for code that asks for it by path.
    added = sorted(n for n in paired if n not in rows)
    new_index, proof = patch_index.append_binary(index, {n: p for n, p in paired.items() if n in records})
    proof['addedBundles'] = added
    proof['addedBundlesWithoutIndexRecord'] = [n for n in added if n not in records]
    proof['indexWasReleaseManifestCopy'] = sha(index) == rows['version.data']['sha256']
    (changes / 'version.data').write_bytes(new_index)
    base_manifest = work / ('manifest-%s.json' % manifest['releaseId'])
    base_manifest.write_bytes(base_bytes)

    sys.path.insert(0, str(remake / 'release/tools'))
    import release_crypto as crypto
    import make_update
    signing = a.signing_dir.resolve()
    signing.mkdir(parents=True, exist_ok=True)
    crypto.JAVA = Path(a.java)
    crypto.PRIVATE, crypto.KEYSTORE, crypto.PASSWORD = signing, signing / 'release.p12', signing / 'password.txt'
    crypto.PUBLIC = signing / 'publisher.der'
    crypto.CLASSES = work / 'signing-classes'
    crypto.RELEASE = work / 'release-scratch'
    (crypto.RELEASE / 'work').mkdir(parents=True, exist_ok=True)
    (crypto.RELEASE / 'reports').mkdir(parents=True, exist_ok=True)
    if not crypto.KEYSTORE.exists():
        # Our own identity with a true name. Remake's prepare() would name a new key after its publisher.
        crypto.PASSWORD.write_text(secrets.token_urlsafe(40) + '\n', encoding='ascii')
        crypto.run([crypto.java_tool('keytool'), '-genkeypair', '-alias', crypto.ALIAS, '-keyalg', 'RSA', '-keysize', '3072',
                    '-sigalg', 'SHA256withRSA', '-validity', '36500', '-storetype', 'PKCS12', '-keystore', crypto.KEYSTORE,
                    '-storepass:file', crypto.PASSWORD, '-keypass:file', crypto.PASSWORD,
                    '-dname', 'CN=GCG2-Offline community update, O=iHealthSi', '-noprompt'])
    sign, verify = crypto.sign, crypto.verify  # their defaults were bound to the publisher's paths
    crypto.sign = lambda data, output: sign(data, output, crypto.KEYSTORE, crypto.PASSWORD, crypto.ALIAS)
    crypto.verify = lambda data, signature: verify(data, signature, crypto.PUBLIC)
    args = make_update.parser().parse_args(
        ['--base-manifest', str(base_manifest), '--changes', str(changes), '--release-id', a.release_id,
         '--output', str(a.out)] + (['--server-payload', str(a.payload)] if a.payload else []))
    result = make_update.build(args)
    # The complete file list of the new release: the base of the next update.
    full = dict(manifest, releaseId=result['releaseId'], baseReleaseId=None, kind='full')
    changed = {r['path']: r for r in result['files']}
    full['files'] = [dict(r, **{k: changed[r['path']][k] for k in ('size', 'sha256')}) if r['path'] in changed else r
                     for r in manifest['files']] + [changed[n] for n in sorted(changed) if n not in rows]
    (a.out.parent / ('manifest-%s.json' % result['releaseId'])).write_bytes(make_update.json_bytes(full))
    identity = json.loads((crypto.RELEASE / 'reports/signing-public.json').read_text(encoding='utf8'))
    print(json.dumps({'releaseId': result['releaseId'], 'baseReleaseId': result['baseReleaseId'],
                      'files': result['files'], 'serverPayload': result['serverPayload'], 'index': proof,
                      'publisher': identity, 'publisherDerSha256': sha(crypto.PUBLIC.read_bytes())}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='stage', required=True)
    s = sub.add_parser('lua')
    s.add_argument('--apk', type=Path, required=True); s.add_argument('--client-dir', type=Path, required=True)
    s.add_argument('--out', type=Path); s.add_argument('--expect-release', action='store_true'); s.add_argument('--tests', action='store_true')
    s.add_argument('--hooks-only', action='store_true', help='patch the released lua.u with the controller and title recipes only')
    s.add_argument('--english-title', action='store_true', help='with --hooks-only: hide the age badge and the notice of the Chinese release')
    s.set_defaults(run=stage_lua)
    s = sub.add_parser('art')
    s.add_argument('--remake-atlas', type=Path, required=True, help='ui_tx/ui_login.u of the installed Remake data')
    s.add_argument('--en-atlas', type=Path, required=True, help='ui_tx/ui_login.u of the English client data')
    s.add_argument('--names', nargs='+', default=['login_bg_title_Mul', 'login_bg_text1_Mul', 'btn_logout_Mul'])
    s.add_argument('--out', type=Path, required=True); s.add_argument('--preview', type=Path)
    s.set_defaults(run=stage_art)
    s = sub.add_parser('server')
    s.add_argument('--apk', type=Path, required=True); s.add_argument('--server-dir', type=Path, required=True)
    s.add_argument('--node-modules', type=Path, required=True); s.add_argument('--remake', type=Path)
    s.add_argument('--work', type=Path, required=True); s.add_argument('--out', type=Path); s.add_argument('--compare-only', action='store_true')
    s.set_defaults(run=stage_server)
    s = sub.add_parser('pack')
    s.add_argument('--apk', type=Path, required=True); s.add_argument('--remake', type=Path, required=True)
    s.add_argument('--lua', type=Path, required=True); s.add_argument('--payload', type=Path)
    s.add_argument('--extra', type=Path, help='folder of more changed bundles at their paths (for example ui_tx/ui_login.u)')
    s.add_argument('--base-manifest', type=Path, help='full manifest of the installed release when it is one of ours (manifest-<id>.json)')
    s.add_argument('--version-data', type=Path, required=True); s.add_argument('--release-id', required=True)
    s.add_argument('--signing-dir', type=Path, required=True); s.add_argument('--java', required=True)
    s.add_argument('--work', type=Path, required=True); s.add_argument('--out', type=Path, required=True)
    s.set_defaults(run=stage_pack)
    a = p.parse_args()
    a.run(a)


if __name__ == '__main__':
    main()
