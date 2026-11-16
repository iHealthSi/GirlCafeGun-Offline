"""apply_update_on_phone.py against a fake phone: success is the installed release id, not the screen.

Run: python tools/remake/test_apply_update_on_phone.py (no phone, no adb).
"""
import io, json, subprocess, sys, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_update_on_phone as tool

FP = 'ab' * 32
UNITY = 'mCurrentFocus=Window{1 u0 com.zirenmidori.gcg.offline/com.unity3d.player.UnityPlayerActivity}'
UPDATE = 'mCurrentFocus=Window{2 u0 com.zirenmidori.gcg.offline/com.zirenmidori.gcg.release.UpdateActivity}'


class Phone:
    """The game, its Update screen and files/release/committed.json."""

    def __init__(self, release, applies=True, state=None):
        self.release, self.applies, self.taps = release, applies, []
        self.state = state                      # raw bytes of committed.json; None: built from release
        self.focus = UNITY

    def run(self, cmd, capture_output=True, timeout=60):
        assert cmd[0] == tool.ADB and cmd[1:] == ['exec-out', 'run-as', tool.PACKAGE, 'cat', tool.STATE], cmd
        if self.state is not None:
            return subprocess.CompletedProcess(cmd, 1, self.state, b'')
        body = json.dumps({'schemaVersion': 1, 'releaseId': self.release, 'manifestSha256': '0' * 64})
        return subprocess.CompletedProcess(cmd, 0, body.encode(), b'')

    def adb(self, *a):
        if a[:2] == ('shell', 'dumpsys window | grep mCurrentFocus'):
            focus, self.focus = self.focus, UNITY if self.focus == UPDATE else self.focus
            return focus
        if a[:3] == ('shell', 'input', 'tap'):
            self.taps.append('update button')
            self.focus = UPDATE
            return ''
        raise AssertionError(a)

    def nodes(self):
        return [('Key fingerprint ' + FP, 1, 1)]

    def tap_text(self, text, wait=20):
        self.taps.append(text)
        if text == 'TRUST ONCE AND APPLY' and self.applies:
            self.release = 'gcg2-0.1.3-22'


def apply(phone, *extra):
    out = io.StringIO()
    with mock.patch.object(tool.subprocess, 'run', phone.run), mock.patch.object(tool, 'adb', phone.adb), \
            mock.patch.object(tool, 'nodes', phone.nodes), mock.patch.object(tool, 'tap_text', phone.tap_text), \
            mock.patch.object(tool.time, 'sleep', lambda s: None), redirect_stdout(out),             mock.patch.object(sys, 'argv', ['apply', '--package-name', 'gcg2-0.1.3-22.gcgupdate', '--fingerprint', FP,
                                            *extra]):
        tool.main()
    return out.getvalue()


class ApplyUpdate(unittest.TestCase):
    def test_applied_when_release_id_changes(self):
        phone = Phone('gcg2-0.1.3-21')
        out = apply(phone)
        self.assertIn('installed release is now gcg2-0.1.3-22 (was gcg2-0.1.3-21)', out)
        self.assertIn('TRUST ONCE AND APPLY', phone.taps)

    def test_game_back_without_new_release_fails(self):
        # The apply fails and the app returns to the game: the old script printed "applied" here.
        phone = Phone('gcg2-0.1.3-21', applies=False)
        with self.assertRaises(SystemExit) as e:
            apply(phone)
        self.assertIn('gcg2-0.1.3-21, not gcg2-0.1.3-22', str(e.exception.code))

    def test_unreadable_state_stops_before_any_tap(self):
        phone = Phone('gcg2-0.1.3-21', state=b'run-as: package not debuggable')
        with self.assertRaises(SystemExit) as e:
            apply(phone)
        self.assertIn('cannot read the installed release id', str(e.exception.code))
        self.assertEqual(phone.taps, [])

    def test_already_installed_taps_nothing(self):
        phone = Phone('gcg2-0.1.3-22')
        self.assertIn('already installed: gcg2-0.1.3-22', apply(phone))
        self.assertEqual(phone.taps, [])

    def test_release_id_from_name_or_option(self):
        self.assertEqual(tool.expected_release('gcg2-0.1.3-22.gcgupdate'), 'gcg2-0.1.3-22')
        self.assertEqual(tool.expected_release('x.zip', 'gcg2-0.1.3-22'), 'gcg2-0.1.3-22')
        with self.assertRaises(SystemExit):
            tool.expected_release('x.zip')
        with self.assertRaises(SystemExit):
            tool.expected_release('../evil.gcgupdate')


if __name__ == '__main__':
    unittest.main()
