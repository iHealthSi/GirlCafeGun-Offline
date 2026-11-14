"""Apply a .gcgupdate that already lies in the game's updates folder, through the game's own Update screen.

The game must show its title screen. The script taps Update, "Updates in game folder", the package and
"Trust once and apply", and prints the key fingerprint that the app shows. It refuses to go on when that
fingerprint is not the one given with --fingerprint (the SHA-256 of our publisher.der).
Only for the owner's phone, and only when the owner asked for the update. adb: C:\\platform-tools\\adb.exe.
MIT, copyright 2026 GCG2-Offline contributors.
"""
import argparse, re, subprocess, sys, time

ADB = r'C:\platform-tools\adb.exe'


def adb(*a):
    return subprocess.run([ADB, *a], capture_output=True, timeout=60).stdout.decode('utf8', 'replace')


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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--package-name', required=True, help='file name in files/updates, for example gcg2-0.1.3-2.gcgupdate')
    p.add_argument('--fingerprint', required=True, help='SHA-256 of our publisher.der, 64 hex digits')
    p.add_argument('--update-button', default='2188,936', help='x,y of the Update button on the title screen')
    a = p.parse_args()
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
            print('applied; the game restarted')
            return
        texts = [t for t, _, _ in nodes()]
        if any(t.startswith('Update completed') for t in texts):
            tap_text('RETURN TO GAME')
        elif texts and not any('UPDATES IN GAME FOLDER' in t for t in texts):
            print('screen:', texts)
    sys.exit('the game did not come back: ' + adb('shell', 'dumpsys window | grep mCurrentFocus'))


if __name__ == '__main__':
    main()
