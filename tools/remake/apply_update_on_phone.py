"""Apply a .gcgupdate that already lies in the game's updates folder, through the game's own Update screen.

The game must show its title screen. The script taps Update, "Updates in game folder", the package and
"Trust once and apply", and prints the key fingerprint that the app shows. It refuses to go on when that
fingerprint is not the one given with --fingerprint (the SHA-256 of our publisher.der).
Success is the installed release id, not the screen: the script reads releaseId from the app's
files/release/committed.json (ReleaseStore.state() of the launcher) before and after, through run-as (our APK
is debuggable; nothing is written), and fails when it is not the release of the package.
Only for the owner's phone, and only when the owner asked for the update. adb: C:\\platform-tools\\adb.exe.
MIT, copyright 2026 GCG2-Offline contributors.
"""
import argparse, json, re, subprocess, sys, time

ADB = r'C:\platform-tools\adb.exe'
PACKAGE = 'com.zirenmidori.gcg.offline'
STATE = 'files/release/committed.json'      # relative to the app's private folder, where run-as starts
SUFFIX = '.gcgupdate'
RELEASE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}')   # ReleaseManifest.identifier()


def adb(*a):
    return subprocess.run([ADB, *a], capture_output=True, timeout=60).stdout.decode('utf8', 'replace')


def installed_release():
    """releaseId of the installed data release, or None when the file cannot be read or holds none."""
    r = subprocess.run([ADB, 'exec-out', 'run-as', PACKAGE, 'cat', STATE], capture_output=True, timeout=60)
    if r.returncode != 0:
        return None
    try:
        state = json.loads(r.stdout.decode('utf8'))
    except ValueError:
        return None
    rid = state.get('releaseId') if isinstance(state, dict) else None
    return rid if isinstance(rid, str) and RELEASE_ID.fullmatch(rid) else None


def expected_release(package_name, release_id=None):
    """The release id the package installs: --release-id, else the file name (build steps name it <id>.gcgupdate)."""
    rid = release_id
    if rid is None:
        if not package_name.endswith(SUFFIX):
            sys.exit('give --release-id: the package name does not end in ' + SUFFIX)
        rid = package_name[:-len(SUFFIX)]
    if not RELEASE_ID.fullmatch(rid):
        sys.exit('not a release id: ' + rid)
    return rid


def nodes():
    adb('shell', 'uiautomator dump /sdcard/ui.xml >/dev/null 2>&1')
    xml = adb('shell', 'cat /sdcard/ui.xml; rm -f /sdcard/ui.xml')
    out = []
    for m in re.finditer(r'<node[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        if m.group(1):
            x0, y0, x1, y1 = map(int, m.groups()[1:])
            out.append((m.group(1).replace('&#10;', '\n'), (x0 + x1) // 2, (y0 + y1) // 2))
    return out


def tap_text(text, wait=20):
    end = time.time() + wait
    while time.time() < end:
        for label, x, y in nodes():
            if label == text:
                adb('shell', 'input', 'tap', str(x), str(y))
                return
        time.sleep(1)
    sys.exit('not on screen: ' + text)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--package-name', required=True, help='file name in files/updates, for example gcg2-0.1.3-2.gcgupdate')
    p.add_argument('--fingerprint', required=True, help='SHA-256 of our publisher.der, 64 hex digits')
    p.add_argument('--update-button', default='2188,936', help='x,y of the Update button on the title screen')
    p.add_argument('--release-id', help='release id the package installs (default: the package name without .gcgupdate)')
    a = p.parse_args(argv)
    expected = expected_release(a.package_name, a.release_id)
    before = installed_release()
    if before is None:
        sys.exit('cannot read the installed release id (%s through run-as %s)' % (STATE, PACKAGE))
    if before == expected:
        print('already installed:', expected)
        return
    print('installed now:', before)
    focus = adb('shell', 'dumpsys window | grep mCurrentFocus')
    if 'com.zirenmidori.gcg.offline/com.unity3d.player.UnityPlayerActivity' not in focus:
        sys.exit('the game is not in front: ' + focus.strip())
    adb('shell', 'input', 'tap', *a.update_button.split(','))
    tap_text('UPDATES IN GAME FOLDER')
    tap_text(a.package_name)
    end = time.time() + 30
    while time.time() < end:
        texts = nodes()
        prompt = [t for t, _, _ in texts if 'fingerprint' in t]
        if prompt:
            shown = re.search(r'[0-9a-f]{64}', prompt[0])
            print('app shows:', shown.group(0) if shown else prompt[0])
            if not shown or shown.group(0) != a.fingerprint.lower():
                tap_text('CANCEL')
                sys.exit('fingerprint differs: cancelled')
            tap_text('TRUST ONCE AND APPLY')
            break
        other = [t for t, _, _ in texts]
        if any('Apply update' in t for t in other):
            sys.exit('the app treats the package as the publisher\'s own: ' + str(other))
        time.sleep(1)
    else:
        sys.exit('no trust prompt: ' + str(nodes()))
    end = time.time() + 90
    while time.time() < end:
        time.sleep(3)
        focus = adb('shell', 'dumpsys window | grep mCurrentFocus')
        if 'UnityPlayerActivity' in focus:
            after = installed_release()
            if after != expected:
                sys.exit('the game is back, but the installed release is %s, not %s: the update was not applied'
                         % (after, expected))
            print('applied: the installed release is now %s (was %s); the game restarted' % (after, before))
            return
        texts = [t for t, _, _ in nodes()]
        if any(t.startswith('Update completed') for t in texts):
            tap_text('RETURN TO GAME')
        elif texts and not any('UPDATES IN GAME FOLDER' in t for t in texts):
            print('screen:', texts)
    sys.exit('the game did not come back: ' + adb('shell', 'dumpsys window | grep mCurrentFocus'))


if __name__ == '__main__':
    main()
