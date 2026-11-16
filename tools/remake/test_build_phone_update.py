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


def main():
    test_new_bundles()
    test_required_entries()
    print('all checks passed')


if __name__ == '__main__':
    main()
