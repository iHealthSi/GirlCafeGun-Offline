"""repack_apk.py: apk stage with fake build tools (no full-size temporary APK stays after a failed step, --dex),
and the Crasheye edit of the sdk-off stage on a synthetic dex (and on our installed repack when it is on this PC).

Run: python tools/remake/test_repack_apk.py (no JDK, no build-tools, no game file).
"""
import argparse, os, shutil, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repack_apk as tool


class FakeTools:
    """zipalign copies; apksigner sign writes a partial output and then fails, or succeeds; verify passes."""

    def __init__(self, sign_fails=False, align_fails=False):
        self.sign_fails, self.align_fails = sign_fails, align_fails

    def __call__(self, args, **kw):
        tool_name = Path(args[0]).name
        if tool_name == 'zipalign.exe':
            if self.align_fails:
                return subprocess.CompletedProcess(args, 1, '', 'zipalign: error')
            shutil.copyfile(args[-2], args[-1])
        elif tool_name == 'apksigner.bat' and args[1] == 'sign':
            out, src = Path(args[args.index('--out') + 1]), Path(args[-1])
            if self.sign_fails:
                out.write_bytes(b'PK half written')
                return subprocess.CompletedProcess(args, 1, '', 'Failed to load signer: keystore password was incorrect')
            shutil.copyfile(src, out)
            Path(str(out) + '.idsig').write_bytes(b'idsig')
        elif tool_name == 'apksigner.bat' and args[1] == 'verify':
            return subprocess.CompletedProcess(args, 0, 'Signer #1 certificate SHA-256 digest: 00\n', '')
        return subprocess.CompletedProcess(args, 0, '', '')


class ApkStage(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.apk = self.dir / 'in.apk'
        with zipfile.ZipFile(self.apk, 'w') as z:
            z.writestr('AndroidManifest.xml', b'manifest')
            z.writestr(tool.DATA, b'old data')
            z.writestr('META-INF/CERT.RSA', b'old signature')
        (self.dir / 'data.unity3d').write_bytes(b'new data')
        self.out = self.dir / 'out' / 'game.apk'

    def stage(self, fake):
        a = argparse.Namespace(apk=self.apk, data=self.dir / 'data.unity3d', signing_dir=self.dir / 'signing',
                               build_tools=str(self.dir / 'bt'), java_home=str(self.dir / 'jdk'), out=self.out,
                               debuggable=False)
        with mock.patch.object(tool.subprocess, 'run', fake), mock.patch('builtins.print'):
            tool.stage_apk(a)

    def left(self):
        return sorted(p.name for p in self.out.parent.iterdir())

    def test_failed_sign_leaves_no_temporary_apk(self):
        with self.assertRaises(SystemExit) as e:
            self.stage(FakeTools(sign_fails=True))
        self.assertIn('keystore password was incorrect', str(e.exception.code))
        self.assertEqual(self.left(), [])          # no unsigned, aligned or half-signed APK

    def test_failed_sign_keeps_an_earlier_output(self):
        self.out.parent.mkdir(parents=True)
        self.out.write_bytes(b'earlier good build')
        with self.assertRaises(SystemExit):
            self.stage(FakeTools(sign_fails=True))
        self.assertEqual(self.left(), ['game.apk'])
        self.assertEqual(self.out.read_bytes(), b'earlier good build')

    def test_failed_align_keeps_an_earlier_output(self):
        self.out.parent.mkdir(parents=True)
        self.out.write_bytes(b'earlier good build')
        with self.assertRaises(SystemExit):
            self.stage(FakeTools(align_fails=True))
        self.assertEqual(self.left(), ['game.apk'])
        self.assertEqual(self.out.read_bytes(), b'earlier good build')

    def test_success_leaves_only_the_signed_apk(self):
        self.stage(FakeTools())
        self.assertEqual(self.left(), ['game.apk'])
        with zipfile.ZipFile(self.out) as z:
            self.assertEqual(z.read(tool.DATA), b'new data')
            self.assertNotIn('META-INF/CERT.RSA', z.namelist())

    def test_dex_replaces_classes_dex_and_nothing_else(self):
        with zipfile.ZipFile(self.apk, 'a') as z:
            z.writestr(tool.DEX, b'old dex')
        (self.dir / 'classes.dex').write_bytes(b'new dex')
        a = argparse.Namespace(apk=self.apk, data=self.dir / 'data.unity3d', dex=self.dir / 'classes.dex',
                               signing_dir=self.dir / 'signing', build_tools=str(self.dir / 'bt'),
                               java_home=str(self.dir / 'jdk'), out=self.out, debuggable=False)
        with mock.patch.object(tool.subprocess, 'run', FakeTools()), mock.patch('builtins.print'):
            tool.stage_apk(a)
        with zipfile.ZipFile(self.out) as z:
            self.assertEqual(z.read(tool.DEX), b'new dex')
            self.assertEqual(z.read(tool.DATA), b'new data')
            self.assertEqual(z.read('AndroidManifest.xml'), b'manifest')


def synthetic_dex(first_units, decoy_units=(0x0612, 0x0439, 0x0008, 0x000E)):
    """A small dex with the tables that dex_method_code reads: Crasheye.init(Context, String, String) and a decoy
    method with the same signature, each with its own code item. Header signature and checksum are valid."""
    import struct
    strings = ['Lcom/xsj/crasheye/Crasheye;', 'init', 'Landroid/content/Context;', 'Ljava/lang/String;', 'Z', 'ZLLL',
               'other']
    s_crasheye, s_init, s_context, s_string, s_z, s_shorty, s_other = range(len(strings))
    types = [s_crasheye, s_context, s_string, s_z]
    t_crasheye, t_context, t_string, t_z = range(len(types))
    header = 0x70
    string_ids = header
    type_ids = string_ids + 4 * len(strings)
    proto_ids = type_ids + 4 * len(types)
    method_ids = proto_ids + 12
    class_defs = method_ids + 8 * 2
    data = class_defs + 32
    body = bytearray(data)
    string_offsets = []
    for text in strings:
        string_offsets.append(len(body))
        body += bytes([len(text)]) + text.encode() + b'\0'
    body += bytes(-len(body) % 4)
    type_list = len(body)
    body += struct.pack('<I3H', 3, t_context, t_string, t_string) + b'\0\0'
    codes = []
    for units in (tuple(first_units) + (0x000E,) * 3, decoy_units):
        body += bytes(-len(body) % 4)
        codes.append(len(body))
        body += struct.pack('<4HII', 7, 3, 2, 0, 0, len(units)) + struct.pack('<%dH' % len(units), *units)
    class_data = len(body)
    # 0 static fields, 0 instance fields, 2 direct methods, 0 virtual methods; method 1 = decoy, method 0 = init
    body += bytes([0, 0, 2, 0])
    for index_diff, code in ((0, codes[1]), (1, codes[0])):
        body += bytes([index_diff, 0x0A])
        while True:  # uleb128 of the code offset
            byte, code = code & 0x7F, code >> 7
            body += bytes([byte | (0x80 if code else 0)])
            if not code:
                break
    body += bytes(-len(body) % 4)
    for i, at in enumerate(string_offsets):
        struct.pack_into('<I', body, string_ids + 4 * i, at)
    for i, s in enumerate(types):
        struct.pack_into('<I', body, type_ids + 4 * i, s)
    struct.pack_into('<3I', body, proto_ids, s_shorty, t_z, type_list)
    struct.pack_into('<HHI', body, method_ids, t_crasheye, 0, s_other)      # method 0: the decoy
    struct.pack_into('<HHI', body, method_ids + 8, t_crasheye, 0, s_init)   # method 1: Crasheye.init
    struct.pack_into('<8I', body, class_defs, t_crasheye, 1, 0xFFFFFFFF, 0, 0xFFFFFFFF, 0, class_data, 0)
    body[:8] = b'dex\n035\0'
    struct.pack_into('<II', body, 32, len(body), header)
    struct.pack_into('<I', body, 40, 0x12345678)
    for at, (n, off) in {56: (len(strings), string_ids), 64: (len(types), type_ids), 72: (1, proto_ids),
                         88: (2, method_ids), 96: (1, class_defs)}.items():
        struct.pack_into('<II', body, at, n, off)
    return tool.dex_with_header(bytes(body)), codes


class CrasheyeOff(unittest.TestCase):
    def test_finds_the_method_by_class_name_and_signature(self):
        dex, codes = synthetic_dex(tool.CRASHEYE_OLD)
        self.assertEqual(tool.dex_method_code(dex, *tool.CRASHEYE), codes[0])
        with self.assertRaises(AssertionError):
            tool.dex_method_code(dex, 'Lcom/xsj/crasheye/Crasheye;', 'init', '(Landroid/content/Context;)Z')

    def test_returns_false_at_once_and_changes_only_two_code_units_and_the_header(self):
        import hashlib, struct, zlib
        dex, codes = synthetic_dex(tool.CRASHEYE_OLD)
        out, proof = tool.crasheye_off(dex)
        insns = codes[0] + 16
        self.assertEqual(struct.unpack_from('<3H', out, insns), (0x0612, 0x060F, 0x0000))  # const/4 v6,0; return v6; nop
        changed = {i for i in range(len(dex)) if dex[i] != out[i]}
        self.assertTrue(all(i < 32 or insns + 2 <= i < insns + 6 for i in changed), sorted(changed))
        self.assertEqual(out[12:32], hashlib.sha1(out[32:]).digest())
        self.assertEqual(int.from_bytes(out[8:12], 'little'), zlib.adler32(out[12:]) & 0xFFFFFFFF)
        # the decoy method with the same signature keeps its code
        self.assertEqual(out[codes[1]:codes[1] + 24], dex[codes[1]:codes[1] + 24])
        self.assertEqual(proof['bytesChangedOutsideHeader'], 3)
        # a second run changes nothing
        again, proof = tool.crasheye_off(out)
        self.assertEqual(again, out)
        self.assertTrue(proof['alreadyPatched'])

    def test_another_build_of_the_method_is_refused(self):
        dex, _ = synthetic_dex((0x0612, 0x0539, 0x0008))
        with self.assertRaises(AssertionError):
            tool.crasheye_off(dex)


# Our installed repack: the copy in dist/ of this checkout, or the file that GCG_REPACK_APK names (for a worktree).
INSTALLED = Path(os.environ.get('GCG_REPACK_APK') or
                 Path(__file__).resolve().parents[2] / 'dist/remake-phone/apk/GCG-Offline-v0.1.3-gcg2-c.apk')


@unittest.skipUnless(INSTALLED.exists(), 'the installed repack is not on this PC')
class OnTheInstalledRepack(unittest.TestCase):
    """The sdk-off edits on the real files of our installed repack: the dex part always, the data part with UnityPy."""

    def test_crasheye_init_of_the_real_dex(self):
        import struct
        with zipfile.ZipFile(INSTALLED) as z:
            dex = z.read(tool.DEX)
        out, proof = tool.crasheye_off(dex)
        self.assertEqual(struct.unpack_from('<3H', out, proof['insnsOffset']), tool.CRASHEYE_NEW)
        self.assertEqual(len(out), len(dex))

    def test_unity_analytics_and_uauto_off_in_the_real_data(self):
        """Needs UnityPy and Remake's asset_tools: GCG_REMAKE names a Remake checkout (release/client)."""
        remake = os.environ.get('GCG_REMAKE')
        if not remake:
            self.skipTest('GCG_REMAKE is not set')
        sys.path.insert(0, str(Path(remake) / 'release/client'))
        try:
            import UnityPy
            import asset_tools
        except ImportError as e:
            self.skipTest('no UnityPy here: %s' % e)
        with zipfile.ZipFile(INSTALLED) as z:
            raw = z.read(tool.DATA)
        data, _ = tool.uauto_off(raw, asset_tools, UnityPy)
        out, proof = tool.analytics_off(data, asset_tools, UnityPy)
        self.assertEqual(proof['bytesChanged'], 3)
        self.assertEqual(set(proof['set'].values()), {'true -> false'})
        _, before = asset_tools.unityfs(data)
        _, after = asset_tools.unityfs(out)
        self.assertEqual(len(before), len(after))
        self.assertEqual(sum(x != y for x, y in zip(before, after)), 3)
        managers = UnityPy.load(out).file.files[tool.ANALYTICS_FILE]
        trees = {o.type.name: o.read_typetree() for o in managers.objects.values()
                 if o.type.name in ('UnityConnectSettings', 'PlayerSettings')}
        self.assertIs(trees['UnityConnectSettings']['m_Enabled'], False)
        self.assertIs(trees['UnityConnectSettings']['UnityAnalyticsSettings']['m_InitializeOnStartup'], False)
        self.assertIs(trees['PlayerSettings']['submitAnalytics'], False)
        # a second run changes nothing; the UAutoSDK object stays inactive
        again, proof = tool.analytics_off(out, asset_tools, UnityPy)
        self.assertEqual((again, proof['bytesChanged']), (out, 0))
        self.assertEqual(tool.uauto_off(out, asset_tools, UnityPy)[1], {'alreadyInactive': True})


if __name__ == '__main__':
    unittest.main()
