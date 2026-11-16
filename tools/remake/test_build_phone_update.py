"""Checks for the pack stage of build_phone_update.py: the new-bundle guard and the
required-entry guard. Plain python, no pytest; runs without a phone, an APK or the
network, on temp data only:

    python tools/remake/test_build_phone_update.py
"""
import io, os, sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_phone_update as b


def test_new_bundles():
    rows = {'lua.u': {'size': 100}, 'ui_tx/ui_login.u': {'size': 200}}
    changed = {'lua.u': None, 'ui_tx/ui_login2.u': None}  # the second name is not a row of the base manifest
    # Default: stop with an error that names the added path
    try:
        b.check_new_bundles(rows, changed, False)
        raise AssertionError('check_new_bundles did not stop for a bundle not in the base manifest')
    except SystemExit as e:
        assert 'ui_tx/ui_login2.u' in str(e), e
    # Allowed: one warning line per added bundle, and the additions are returned
    out = io.StringIO()
    with redirect_stdout(out):
        added = b.check_new_bundles(rows, changed, True)
    lines = [l for l in out.getvalue().splitlines() if l]
    assert added == ['ui_tx/ui_login2.u'], added
    assert lines == ['warning: new bundle not in the base manifest: ui_tx/ui_login2.u'], lines
    # Nothing added: no error and no warning
    out = io.StringIO()
    with redirect_stdout(out):
        added = b.check_new_bundles(rows, {'lua.u': None}, False)
    assert added == [] and out.getvalue() == '', (added, out.getvalue())


def test_required_entries():
    names = {'dist/index.js', 'resources/web/notice/index.html'}
    assert b.check_required_entries(names, ['resources/web/notice/index.html']) == []
    assert b.check_required_entries(names, []) == []
    # One required name missing: stop with an error that names it, and only it
    try:
        b.check_required_entries(names, ['resources/web/notice/index.html', 'resources/web/notice.txt'])
        raise AssertionError('check_required_entries did not stop for a missing entry')
    except SystemExit as e:
        assert 'resources/web/notice.txt' in str(e), e
        assert 'resources/web/notice/index.html' not in str(e), e


def test_english_text():
    (old, new), = b.CN_TEXT['UI_CafeItemTips.lua']
    src = ('x = 1\r\n        a.text =\r\n            ' + old + '\r\n').encode('utf8')
    out = b.english_text_script('UI_CafeItemTips.lua', src).decode('utf8')
    assert new in out and old not in out and '点' not in out, out
    assert b.english_text_script('UI_CafeItemTips.lua', out.encode('utf8')).decode('utf8') == out  # twice = once
    try:
        b.english_text_script('UI_CafeItemTips.lua', b'nothing here')
        raise AssertionError('english_text_script did not stop on a script without the line')
    except AssertionError as e:
        assert 'did not stop' not in str(e), e


def test_text_art_helpers():
    try:
        from PIL import Image
        import numpy  # noqa: F401
    except ImportError:
        print('skip text_art helpers: PIL or numpy missing'); return
    import text_art as t
    assert t.is_mul('common_button_back_Mul') and t.is_mul('towerWarChess_title_MUL') and not t.is_mul('icon_giftbox21')
    a = Image.new('RGBA', (20, 10), (255, 0, 0, 255))
    assert t.differs(a, a.copy()) == 0.0 and t.differs(a, Image.new('RGBA', (10, 10))) == 1.0
    c = a.copy(); c.paste((0, 0, 255, 255), (0, 0, 2, 1))  # 2 of 200 pixels: 1 %
    assert abs(t.differs(a, c) - 0.01) < 1e-9
    # clear pixels count as equal whatever their colour
    assert t.differs(Image.new('RGBA', (4, 4), (255, 0, 0, 0)), Image.new('RGBA', (4, 4), (0, 255, 0, 0))) == 0.0
    # fit: a small picture keeps its own padding, centred; a big one is cropped to its visible pixels, then scaled down
    small = Image.new('RGBA', (6, 4), (0, 0, 0, 0)); small.paste((9, 9, 9, 255), (1, 1, 3, 3))
    canvas, drawn = t.fit(small, 10, 8)
    assert canvas.size == (10, 8) and drawn == [6, 4] and canvas.getchannel('A').getbbox() == (3, 3, 5, 5)
    big = Image.new('RGBA', (40, 20), (0, 0, 0, 0)); big.paste((9, 9, 9, 255), (0, 5, 40, 15))
    canvas, drawn = t.fit(big, 20, 20)
    assert drawn == [20, 5] and canvas.getchannel('A').getbbox() == (0, 7, 20, 12), (drawn, canvas.getchannel('A').getbbox())


def main():
    test_new_bundles()
    test_required_entries()
    test_english_text()
    test_text_art_helpers()
    print('all checks passed')


if __name__ == '__main__':
    main()
