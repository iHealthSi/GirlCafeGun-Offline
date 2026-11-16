"""Swap the Chinese text art of the Remake client data for the English art of our EN client data.

Remake's client is the Chinese package (zh_CN). Its text table is English, but art with words in it is Chinese.
The game names such art with `_Mul` ("multi-language"): `common_button_back_Mul` is the 返回 back button,
`event_actbig42_Mul` an event banner. The EN client (build 179, `assets/Bundles`) holds the same names with
English words. This module paints the English pixels into the phone's own bundles:

- Atlas sprites (`ui_tx/*.u`, one SpriteAtlas, rectangle packing, no rotation, no alpha texture): the EN sprite
  goes into the CN sprite's rectangle (cropped to its visible pixels, scaled down to fit, centred). Only the
  4x4 blocks that the rectangles touch are encoded again; every other byte of the atlas stays.
- Standalone textures (`*_Mul` Texture2D anywhere in the given folders): same size and format = the EN bytes
  as they are (lossless); same size, other format = EN pixels encoded in the CN format; other size = the EN
  sprite painted into each CN sprite rectangle of that texture, or the EN picture scaled to the CN size.

Rows, keys, object ids, sprite rectangles and texture formats of the CN bundles do not change, so prefabs bind
as before. Names are matched over all given EN folders (the two data sets split `*_more.u` bundles in other
ways). A pair is taken only when the pictures differ: share of pixels with a channel off by more than 40
(alpha-weighted) above 0.2 %. Non-`_Mul` art is never touched: with the same name it is often other art
(gift boxes, CGs) of the other region.

Run it on data that still holds the Chinese pictures. On data from an earlier run it swaps some pictures again:
a picture that was painted or encoded here differs from its EN twin by encoder noise (2-5 % of pixels), which
is as large as some real differences (`common_icon_captain_Mul`: 0.5 %). It is harmless, only larger. After
release gcg2-0.1.3-25, pass --only with the bundles that changed since.

Nothing here downloads anything or talks to the phone. MIT, copyright 2026 GCG2-Offline contributors.
"""
from __future__ import annotations
import functools, hashlib, json
from pathlib import Path

TOL, SHARE = 40, 0.002


def is_mul(name):
    return 'mul' in name.lower()


def bundles(root, folders):
    for f in folders:
        p = root / f
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from sorted(x for x in p.rglob('*.u') if x.is_file())


def differs(a, b):
    """Share of visible pixels where the two pictures differ (1.0 when sizes differ)."""
    import numpy as np
    if a.size != b.size:
        return 1.0
    A = np.asarray(a.convert('RGBA'), dtype=np.int32); B = np.asarray(b.convert('RGBA'), dtype=np.int32)
    pa = A[..., :3] * A[..., 3:] // 255; pb = B[..., :3] * B[..., 3:] // 255
    d = np.maximum(np.abs(pa - pb).max(axis=2), np.abs(A[..., 3] - B[..., 3]))
    return float((d > TOL).mean())


def fit(art, w, h):
    """Centre art on a clear w x h canvas. When it does not fit: crop it to its visible pixels first, then scale
    it down (never up)."""
    from PIL import Image
    art = art.convert('RGBA')
    box = art.getchannel('A').getbbox()
    if box and (art.width > w or art.height > h):
        art = art.crop(box)
    s = min(w / art.width, h / art.height, 1.0)
    size = (max(1, round(art.width * s)), max(1, round(art.height * s)))
    if size != art.size:
        art = art.resize(size, Image.LANCZOS)
    canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    canvas.paste(art, ((w - size[0]) // 2, (h - size[1]) // 2))
    return canvas, list(size)


BLOCK = {45: 8, 47: 16, 34: 8, 41: 8, 33: 8, 64: 8}  # ETC2_RGB, ETC2_RGBA8, ETC_RGB4, EAC... bytes per 4x4 block


def encode(tex, img, mips):
    from UnityPy.export import Texture2DConverter
    platform = tex.object_reader.platform if tex.object_reader is not None else 0
    data, fmt = Texture2DConverter.image_to_texture2d(img, tex.m_TextureFormat, platform, tex.m_PlatformBlob)
    assert int(fmt) == int(tex.m_TextureFormat), (tex.m_Name, fmt, tex.m_TextureFormat)
    if mips > 1:
        from PIL import Image
        w, h, cur = img.width, img.height, img
        for _ in range(mips - 1):
            w, h = max(1, w // 2), max(1, h // 2)
            cur = cur.resize((w, h), Image.BICUBIC)
            data += Texture2DConverter.image_to_texture2d(cur, tex.m_TextureFormat, platform, tex.m_PlatformBlob)[0]
    return data


def store(env, tex, data):
    """Put new image bytes into the texture. When the texture streams from a .resS of this bundle and the length
    is the same, the bytes go over the old ones in that stream (the bundle does not grow, no field changes).
    Else the bytes go inline and the stream reference is cleared. Returns 'stream' or 'inline'."""
    import ntpath
    from UnityPy.streams import EndianBinaryReader
    sd = tex.m_StreamData
    if sd is not None and sd.path and sd.size == len(data):
        name = ntpath.basename(sd.path)
        old = env.file.files.get(name)
        if old is not None and not hasattr(old, 'objects'):
            buf = bytearray(old.bytes)
            assert sd.offset + sd.size <= len(buf)
            buf[sd.offset:sd.offset + sd.size] = data
            new = EndianBinaryReader(bytes(buf), endian=old.endian)
            for attr in ('flags', 'name'):  # the bundle writer needs the node flags of every file
                if hasattr(old, attr):
                    setattr(new, attr, getattr(old, attr))
            env.file.files[name] = new
            for key, value in list(env.cabs.items()):
                if value is old:
                    env.cabs[key] = new
            return 'stream'
    put_bytes(tex, data)
    tex.save()
    return 'inline'


def put_bytes(tex, data):
    tex.image_data = bytes(data)
    tex.m_CompleteImageSize = len(data)
    if tex.m_StreamData is not None:
        tex.m_StreamData.path = ''; tex.m_StreamData.offset = 0; tex.m_StreamData.size = 0


def splice(tex, new_img, rects):
    """Encode new_img in the texture's format, keep the old bytes of every 4x4 block that no rect touches.
    rects are Unity rectangles (x, y from the bottom). Returns (bytes, number of blocks written)."""
    fmt = int(tex.m_TextureFormat)
    old = bytes(tex.get_image_data())
    W, H = tex.m_Width, tex.m_Height
    if fmt == 4:  # RGBA32: no blocks, every untouched pixel is written back as it was
        return encode(tex, new_img, 1), 0
    bpb = BLOCK[fmt]
    assert (tex.m_MipCount or 1) == 1 and W % 4 == 0 and H % 4 == 0 and len(old) == W * H // 16 * bpb, tex.m_Name
    new = encode(tex, new_img, 1)
    assert len(new) == len(old)
    out = bytearray(old); bw = W // 4; n = 0
    for x, y, w, h in rects:
        for by in range(y // 4, (y + h - 1) // 4 + 1):
            for bx in range(x // 4, (x + w - 1) // 4 + 1):
                i = (by * bw + bx) * bpb
                out[i:i + bpb] = new[i:i + bpb]; n += 1
    return bytes(out), n


class EnIndex:
    """Names of the EN client data: *_Mul textures and sprites over all given folders."""

    def __init__(self, root, folders):
        import UnityPy
        self.root = root
        self.tex, self.sprite = {}, {}
        for f in bundles(root, folders):
            env = UnityPy.load(str(f))
            for o in env.objects:
                if o.type.name not in ('Texture2D', 'Sprite'):
                    continue
                try:
                    n = o.peek_name()
                except Exception:
                    continue
                if n and is_mul(n):
                    (self.tex if o.type.name == 'Texture2D' else self.sprite).setdefault(n, []).append((f, o.path_id))

    @functools.lru_cache(maxsize=8)
    def env(self, path):
        import UnityPy
        return UnityPy.load(str(path))

    def read(self, ref):
        path, pid = ref
        return next(o for o in self.env(path).objects if o.path_id == pid).read()

    def texture(self, name):
        refs = self.tex.get(name)
        return self.read(refs[0]) if refs else None

    def sprite_image(self, name):
        refs = self.sprite.get(name)
        return self.read(refs[0]).image.convert('RGBA') if refs else None


def plain(key):
    guid, file_id = key
    return tuple(getattr(guid, 'data_%d_' % i) for i in range(4)), file_id


def atlas_pass(env, en_bundle, en, rel, report):
    """Paint the EN *_Mul sprites of the same ui_tx bundle into the CN atlas. Returns True when changed."""
    import UnityPy
    atlases = [o.read() for o in env.objects if o.type.name == 'SpriteAtlas']
    if not atlases or en_bundle is None or not en_bundle.exists():
        return False
    assert len(atlases) == 1, rel
    atlas = atlases[0]
    m = atlas.m_RenderDataMap
    items = list(m.items()) if hasattr(m, 'items') else list(m)
    rd = {plain(k): v for k, v in items}
    for v in rd.values():
        # rectangle packing, no rotation, full-rect mesh, no alpha texture: painting a rect shows all of it
        assert v.settingsRaw & 3 == 3 and (v.settingsRaw >> 2) & 15 == 0 and v.alphaTexture.m_PathID == 0, (rel, v.settingsRaw)
    texes = {o.path_id: o for o in env.objects if o.type.name == 'Texture2D'}
    sprites = {}
    for o in env.objects:
        if o.type.name == 'Sprite':
            s = o.read(); sprites[s.m_Name] = s
    en_env = UnityPy.load(str(en_bundle))
    en_sprites = {}
    for o in en_env.objects:
        if o.type.name == 'Sprite':
            s = o.read()
            if is_mul(s.m_Name):
                en_sprites[s.m_Name] = s
    jobs = {}  # texture path id -> [(name, rect, art)]
    for name, s in sorted(sprites.items()):
        if not is_mul(name) or name not in en_sprites:
            continue
        cn_img = s.image.convert('RGBA'); en_img = en_sprites[name].image.convert('RGBA')
        share = differs(cn_img, en_img)
        if share <= SHARE:
            continue
        v = rd[plain(s.m_RenderDataKey)]
        r = v.textureRect
        rect = (round(r.x), round(r.y), round(r.width), round(r.height))
        jobs.setdefault(v.texture.m_PathID, []).append((name, rect, en_img, share))
    if not jobs:
        return False
    for pid, rows in jobs.items():
        tex = texes[pid].read()
        base = tex.image.convert('RGBA'); before = base.copy()
        H = base.height
        all_rects = [tuple(round(t) for t in (v.textureRect.x, v.textureRect.y, v.textureRect.width, v.textureRect.height))
                     for v in rd.values() if v.texture.m_PathID == pid]
        for name, (x, y, w, h), art, share in rows:
            for o in all_rects:  # no other sprite may share pixels with this one
                if o != (x, y, w, h):
                    assert x + w <= o[0] or o[0] + o[2] <= x or y + h <= o[1] or o[1] + o[3] <= y, (rel, name, o)
            canvas, drawn = fit(art, w, h)
            base.paste(canvas, (x, H - (y + h)))
            report.append({'bundle': rel, 'kind': 'atlas', 'name': name, 'rect': [x, y, w, h], 'cn': [w, h],
                           'en': list(art.size), 'drawn': drawn, 'share': round(share, 4)})
        data, blocks = splice(tex, base, [r[1] for r in rows])
        where = store(env, tex, data)
        # read back: inside the painted rects close to the paint, outside every block as before
        import numpy as np
        after = texes[pid].read().image.convert('RGBA')
        A = np.asarray(after, dtype=np.int16); B = np.asarray(before, dtype=np.int16); P = np.asarray(base, dtype=np.int16)
        mask = np.zeros(A.shape[:2], bool)
        for _, (x, y, w, h), _, _ in rows:
            x0, x1 = x // 4 * 4, ((x + w - 1) // 4 + 1) * 4; y0, y1 = y // 4 * 4, ((y + h - 1) // 4 + 1) * 4
            mask[H - y1:H - y0, x0:x1] = True
        assert (A[~mask] == B[~mask]).all(), (rel, 'a pixel outside the touched blocks changed')
        assert np.abs(A[mask] - P[mask]).mean() < 6, (rel, 'the painted rects do not read back')
        report.append({'bundle': rel, 'kind': 'atlas-texture', 'name': tex.m_Name, 'blocksWritten': blocks, 'where': where})
    return True


def texture_pass(env, en, rel, report, missing):
    """Swap every standalone *_Mul texture of the bundle for its EN twin. Returns True when changed."""
    from PIL import Image
    atlas_tex = set()
    for o in env.objects:
        if o.type.name == 'SpriteAtlas':
            m = o.read().m_RenderDataMap
            for k, v in (m.items() if hasattr(m, 'items') else m):
                atlas_tex.add(v.texture.m_PathID)
    sprites_of = {}
    for o in env.objects:
        if o.type.name == 'Sprite':
            s = o.read()
            sprites_of.setdefault(s.m_RD.texture.m_PathID, []).append(s)
    changed = False
    for o in env.objects:
        if o.type.name != 'Texture2D' or o.path_id in atlas_tex:
            continue
        try:
            name = o.peek_name()
        except Exception:
            continue
        if not name or not is_mul(name):
            continue
        en_tex = en.texture(name)
        if en_tex is None:
            missing.append({'bundle': rel, 'name': name}); continue
        tex = o.read()
        cn_img = tex.image.convert('RGBA'); en_img = en_tex.image.convert('RGBA')
        share = differs(cn_img, en_img)
        if share <= SHARE:
            continue
        mips = tex.m_MipCount or 1
        row = {'bundle': rel, 'kind': 'texture', 'name': name, 'cn': list(cn_img.size), 'en': list(en_img.size),
               'format': int(tex.m_TextureFormat), 'share': round(share, 4)}
        if cn_img.size == en_img.size:
            if int(en_tex.m_TextureFormat) == int(tex.m_TextureFormat) and (en_tex.m_MipCount or 1) == mips:
                data = bytes(en_tex.get_image_data()); row['how'] = 'en bytes'
            else:
                data = encode(tex, en_img, mips); row['how'] = 'encoded'
        else:
            W, H = cn_img.size
            parts = [s for s in sprites_of.get(o.path_id, [])
                     if (round(s.m_Rect.width), round(s.m_Rect.height)) != (W, H)]
            if parts:
                img = cn_img.copy()
                for s in parts:
                    r = s.m_RD.textureRect
                    x, y, w, h = round(r.x), round(r.y), round(r.width), round(r.height)
                    art = en.sprite_image(s.m_Name) or en_img
                    canvas, _ = fit(art, w, h)
                    img.paste(canvas, (x, H - (y + h)))
                row['how'] = 'painted into %d sprite rects' % len(parts)
            else:
                aspect = (en_img.width / en_img.height) / (W / H)
                row['aspect'] = round(aspect, 3)
                if abs(aspect - 1) <= 0.03:
                    img = en_img.resize((W, H), Image.LANCZOS); row['how'] = 'scaled'
                else:  # other shape: keep the EN proportions, centred on the CN canvas
                    img, drawn = fit(en_img, W, H); row['how'] = 'fitted'; row['drawn'] = drawn
            data = encode(tex, img, mips)
        row['where'] = store(env, tex, data)
        back = o.read().image.convert('RGBA')
        assert back.size == cn_img.size, (rel, name)
        if row['how'] in ('en bytes', 'encoded'):
            row['readBack'] = round(differs(back, en_img), 4)
            assert row['readBack'] <= 0.02, (rel, name, row['readBack'])
        report.append(row)
        changed = True
    return changed


def run(cn_root: Path, en_root: Path, folders, out: Path, report_path: Path, only=None, preview: Path | None = None):
    import UnityPy
    en = EnIndex(en_root, folders)
    report, missing, written = [], [], []
    for f in bundles(cn_root, folders):
        rel = str(f.relative_to(cn_root)).replace('\\', '/')
        if only and rel not in only:
            continue
        env = UnityPy.load(str(f))
        changed = atlas_pass(env, en_root / rel, en, rel, report)
        changed = texture_pass(env, en, rel, report, missing) or changed
        if not changed:
            continue
        blob = env.file.save(packer='original')
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        check = UnityPy.load(str(dest))  # reads back with the same objects
        assert sorted(o.path_id for o in check.objects) == sorted(o.path_id for o in env.objects), rel
        written.append({'bundle': rel, 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                        'sourceSha256': hashlib.sha256(f.read_bytes()).hexdigest()})
        print(rel, flush=True)
    result = {'written': written, 'changed': report, 'noEnglishTwin': missing}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'bundles': len(written), 'pictures': sum(r['kind'] != 'atlas-texture' for r in report),
                      'noEnglishTwin': len(missing), 'report': str(report_path)}))
    if preview:
        sheet(cn_root, out, result, preview)
    return result


def sheet(cn_root, out, result, preview):
    """Before (left) and after (right) of every changed picture, one or more JPEG pages."""
    import UnityPy
    from PIL import Image, ImageDraw
    preview.mkdir(parents=True, exist_ok=True)
    rows = [r for r in result['changed'] if r['kind'] in ('atlas', 'texture')]

    def pictures(path):
        env = UnityPy.load(str(path)); pics = {}
        for o in env.objects:
            if o.type.name in ('Sprite', 'Texture2D'):
                try:
                    d = o.read()
                except Exception:
                    continue
                if is_mul(d.m_Name):
                    try:
                        pics[(o.type.name, d.m_Name)] = d.image.convert('RGBA')
                    except Exception:
                        pass
        return pics
    cache = {}
    page = Image.new('RGB', (1400, 1800), (40, 40, 40)); dr = ImageDraw.Draw(page); y = 0; n = 0
    for r in rows:
        if r['bundle'] not in cache:
            cache.clear(); cache[r['bundle']] = (pictures(cn_root / r['bundle']), pictures(out / r['bundle']))
        b, a = cache[r['bundle']]
        key = ('Sprite' if r['kind'] == 'atlas' else 'Texture2D', r['name'])
        if key not in b or key not in a:
            continue
        def small(im):
            s = min(110 / im.height, 640 / im.width, 2.0)
            return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
        L, R = small(b[key]), small(a[key])
        h = max(L.height, R.height) + 16
        if y + h > page.height:
            page.save(preview / f'sheet_{n:02d}.jpg', quality=85); n += 1
            page = Image.new('RGB', (1400, 1800), (40, 40, 40)); dr = ImageDraw.Draw(page); y = 0
        dr.text((4, y), f"{r['bundle']}  {r['name']}", fill=(255, 255, 0))
        page.paste(L, (4, y + 14), L); page.paste(R, (700, y + 14), R)
        y += h + 2
    page.save(preview / f'sheet_{n:02d}.jpg', quality=85)
