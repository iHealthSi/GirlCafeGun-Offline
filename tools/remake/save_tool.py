"""Save management for the Remake phone build: back the save up to this PC, put a stored save on the phone, wipe it.

The save is one file in the private storage of the app (files/gcg-server/data/state.json). The game code has no
part in this: the tool reads and writes the file with `adb shell run-as <package>`, which Android allows only for
an APK with android:debuggable (tools/remake/repack_apk.py apk --debuggable). Saves live on the PC, outside git,
in saves-backup/remake/<time>[-label]/.

Commands:
  status                phone: can the tool reach the save, is there one; and the saves on the PC
  list                  the saves on the PC
  backup [--label L]    copy the phone's save (and the server's daily copies) to the PC. The game may run.
  push <save>           put a PC save on the phone. <save> is a folder name from `list`, a part of one, or a .json file
  wipe                  remove the save on the phone; the game makes a new one at its next start

push and wipe stop the game first and always back the phone's save up to the PC before they change it.
Only for the owner's phone, and only when the owner asked. adb: C:\\platform-tools\\adb.exe.
MIT, copyright 2026 GCG2-Offline contributors.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys, time
from pathlib import Path

PACKAGE = 'com.zirenmidori.gcg.offline'
DATA = 'files/gcg-server/data'          # relative to the app's private folder, where run-as starts
SAVE = DATA + '/state.json'
DAILY = DATA + '/backups'
TEMP = '/data/local/tmp/gcg-save-in.json'
STORE = Path(__file__).resolve().parents[2] / 'saves-backup' / 'remake'
sha = lambda b: hashlib.sha256(b).hexdigest()


class Phone:
    def __init__(self, adb, package):
        self.adb, self.package = adb, package

    def run(self, *args, binary=False):
        r = subprocess.run([self.adb, *args], capture_output=True, timeout=120)
        out = r.stdout if binary else r.stdout.decode('utf8', 'replace').replace('\r\n', '\n')
        return r.returncode, out, r.stderr.decode('utf8', 'replace')

    def app(self, command):
        """Run a shell command as the app, inside its private folder."""
        code, out, err = self.run('shell', 'run-as %s sh -c "%s"; echo __rc=$?' % (self.package, command))
        m = re.search(r'__rc=(\d+)\s*$', out)
        return (int(m.group(1)) if m else 1), (out[:m.start()] if m else out + err)

    def check(self):
        code, out, err = self.run('get-state')
        if code or 'device' not in out:
            sys.exit('no phone on adb (%s)' % (out + err).strip())
        code, out, _ = self.run('shell', 'pm path ' + self.package)
        if 'package:' not in out:
            sys.exit(self.package + ' is not installed on the phone')
        code, out = self.app('echo ok')
        if code or 'ok' not in out:
            sys.exit('the tool cannot reach the save: %s\nThe installed APK is not debuggable. Build one with\n'
                     '  tools\\remake\\repack_apk.py apk ... --debuggable\nand install it with adb install -r (the save stays).'
                     % out.strip())

    def has_save(self):
        # A failed adb call must not look like "no save": push and wipe go ahead on that answer.
        out = self.app('test -f %s && echo yes || echo no' % SAVE)[1].strip()
        if out not in ('yes', 'no'):
            sys.exit('cannot tell whether the phone has a save (raw output: %r): stopped, nothing changed' % out)
        return out == 'yes'

    def read(self, path):
        code, out, err = self.run('exec-out', 'run-as', self.package, 'cat', path, binary=True)
        if code:
            sys.exit('cannot read %s: %s' % (path, err))
        return out

    def daily(self):
        # A failed listing must not look like "no daily copies": push and wipe delete that folder next.
        code, out = self.app('if [ -d %s ]; then ls %s; else echo __none; fi' % (DAILY, DAILY))
        if code == 0 and out.strip() == '__none':
            return []
        names = out.split()
        if code or '__none' in names or any(not re.fullmatch(r'[A-Za-z0-9._-]+', n) for n in names):
            sys.exit('cannot list the daily copies on the phone (raw output: %r): stopped, nothing changed' % out)
        return names

    def stop(self):
        self.run('shell', 'am', 'force-stop', self.package)
        time.sleep(1)

    def model(self):
        return self.run('shell', 'getprop', 'ro.product.model')[1].strip()


def saves(store):
    rows = []
    for folder in sorted(p for p in store.iterdir() if (p / 'state.json').is_file()) if store.is_dir() else []:
        body = (folder / 'state.json').read_bytes()
        info = json.loads((folder / 'info.json').read_text(encoding='utf8')) if (folder / 'info.json').is_file() else {}
        rows.append({'name': folder.name, 'bytes': len(body), 'sha256': sha(body), 'label': info.get('label', ''),
                     'path': folder / 'state.json'})
    return rows


def show(rows):
    if not rows:
        print('  (none)')
    for r in rows:
        print('  %-42s %9d bytes  %s  %s' % (r['name'], r['bytes'], r['sha256'][:12], r['label']))


def looks_like_a_save(body):
    try:
        return isinstance(json.loads(body.decode('utf8')), dict)
    except (UnicodeDecodeError, ValueError):
        return False


def new_folder(store, label):
    label = re.sub(r'[^A-Za-z0-9_-]+', '-', label or '').strip('-')
    folder = store / (time.strftime('%Y%m%d-%H%M%S') + ('-' + label if label else ''))
    while folder.exists():  # two backups in one second
        folder = folder.with_name(folder.name + '-b')
    folder.mkdir(parents=True)
    return folder, label


def add_daily_copies(phone, folder):
    """Copy the phone's daily copies that folder does not hold yet, before push or wipe deletes them.
    Returns (how many were added, all stored copies). A copy the server rewrote under the same name is kept
    next to the old one as <name>-<sha8>.json."""
    info_path = folder / 'info.json'
    info = json.loads(info_path.read_text(encoding='utf8')) if info_path.is_file() else {}
    copies = dict(info.get('dailyCopies') or {})
    added = 0
    for name in phone.daily():
        copy = phone.read(DAILY + '/' + name)
        if not looks_like_a_save(copy):
            sys.exit('the daily copy %s on the phone is not a JSON object: stopped, nothing changed' % name)
        if sha(copy) in copies.values():
            continue
        stored = name
        if stored in copies:
            stem, dot, ext = name.rpartition('.')
            stored = '%s-%s.%s' % (stem, sha(copy)[:8], ext) if dot else '%s-%s' % (name, sha(copy)[:8])
        (folder / 'phone-daily-copies').mkdir(exist_ok=True)
        (folder / 'phone-daily-copies' / stored).write_bytes(copy)
        copies[stored] = sha(copy)
        added += 1
    if added:
        info['dailyCopies'] = copies
        info_path.write_text(json.dumps(info, indent=2) + '\n', encoding='utf8')
    return added, copies


def backup(phone, store, label, why=''):
    """Copy the phone's save and its daily copies to the PC. Returns the folder, or None when the phone has neither."""
    if not phone.has_save():
        print('the phone has no save: nothing to back up')
        if not phone.daily():
            return None
        folder, label = new_folder(store, (label or '') + '-daily-only')
        (folder / 'info.json').write_text(json.dumps({'when': time.strftime('%Y-%m-%d %H:%M:%S'), 'label': label,
                                                      'reason': why, 'phone': phone.model()}, indent=2) + '\n',
                                          encoding='utf8')
        print('daily copies only: %s, added %d daily copies' % (folder, add_daily_copies(phone, folder)[0]))
        return folder
    body = phone.read(SAVE)
    if not looks_like_a_save(body):
        sys.exit('the save on the phone is not a JSON object (%d bytes): stopped, nothing changed' % len(body))
    same = [r for r in saves(store) if r['sha256'] == sha(body)]
    if same:
        folder = same[-1]['path'].parent
        added = add_daily_copies(phone, folder)[0]
        print('the phone\'s save is already on the PC as %s (already stored), added %d daily copies' % (folder.name, added))
        return folder
    folder, label = new_folder(store, label)
    (folder / 'state.json').write_bytes(body)
    info = {'when': time.strftime('%Y-%m-%d %H:%M:%S'), 'label': label, 'reason': why, 'phone': phone.model(),
            'package': phone.package, 'bytes': len(body), 'sha256': sha(body), 'dailyCopies': {}}
    (folder / 'info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf8')
    copies = add_daily_copies(phone, folder)[1]
    assert (folder / 'state.json').read_bytes() == body
    print('backed up: %s (%d bytes, sha256 %s, %d daily copies)' % (folder, len(body), sha(body)[:12], len(copies)))
    return folder


def cmd_status(a, phone):
    phone.check()
    if phone.has_save():
        body = phone.read(SAVE)
        known = [r['name'] for r in saves(a.store) if r['sha256'] == sha(body)]
        print('phone (%s): save of %d bytes, sha256 %s, %s' % (phone.model(), len(body), sha(body)[:12],
              'on the PC as ' + known[-1] if known else 'NOT on the PC yet'))
    else:
        print('phone (%s): no save; the game makes a new one at its next start' % phone.model())
    print('daily copies on the phone: %d' % len(phone.daily()))
    print('saves on the PC (%s):' % a.store)
    show(saves(a.store))


def cmd_list(a, phone):
    print('saves on the PC (%s):' % a.store)
    show(saves(a.store))


def cmd_backup(a, phone):
    phone.check()
    backup(phone, a.store, a.label)


def pick(a):
    path = Path(a.save)
    if path.is_file():
        return path
    rows = saves(a.store)
    hits = [r for r in rows if r['name'] == a.save] or [r for r in rows if a.save in r['name'] or a.save == r['label']]
    if len(hits) != 1:
        print('saves on the PC:'); show(rows)
        sys.exit('"%s" names %d saves: give one folder name' % (a.save, len(hits)))
    return hits[0]['path']


def cmd_push(a, phone):
    source = pick(a)
    body = source.read_bytes()
    if not looks_like_a_save(body):
        sys.exit('%s is not a JSON object: not a save of this game' % source)
    phone.check()
    phone.stop()
    backup(phone, a.store, 'before-push', why='before push of ' + source.parent.name)
    code, out, err = phone.run('push', str(source), TEMP)
    if code:
        sys.exit('adb push failed: ' + out + err)
    # Copy as the app, then rename: the game never sees a half-written file. The daily copies of the
    # other save go away (they are on the PC now), so the server does not mix two saves.
    code, out = phone.app('mkdir -p %s && cp %s %s.pc && mv %s.pc %s && rm -rf %s' % (DATA, TEMP, SAVE, SAVE, SAVE, DAILY))
    phone.run('shell', 'rm', '-f', TEMP)
    if code:
        sys.exit('could not write the save on the phone: ' + out)
    if phone.read(SAVE) != body:
        sys.exit('the save on the phone differs from %s after the copy' % source)
    print('on the phone now: %s (%d bytes, sha256 %s). Start the game.' % (source, len(body), sha(body)[:12]))


def cmd_wipe(a, phone):
    phone.check()
    phone.stop()
    backup(phone, a.store, 'before-wipe', why='before wipe')
    code, out = phone.app('rm -f %s && rm -rf %s' % (SAVE, DAILY))
    if code or phone.has_save():
        sys.exit('could not remove the save on the phone: ' + out)
    print('the phone has no save now. The game makes a new one at its next start.')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--adb', default=r'C:\platform-tools\adb.exe')
    p.add_argument('--package', default=PACKAGE)
    p.add_argument('--store', type=Path, default=STORE, help='folder of the saves on the PC (default: saves-backup/remake)')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('status').set_defaults(run=cmd_status)
    sub.add_parser('list').set_defaults(run=cmd_list)
    s = sub.add_parser('backup'); s.add_argument('--label', default=''); s.set_defaults(run=cmd_backup)
    s = sub.add_parser('push'); s.add_argument('save'); s.set_defaults(run=cmd_push)
    sub.add_parser('wipe').set_defaults(run=cmd_wipe)
    a = p.parse_args()
    a.run(a, Phone(a.adb, a.package))


if __name__ == '__main__':
    main()
