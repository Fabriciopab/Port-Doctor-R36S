"""Read-only Unity integrity diagnostics, including hostile manifest paths."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('unity_audit', Path(__file__).parent / 'portdoctor/tools/unity_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class UnityAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'META-INF').mkdir()
        self.manifest = self.root / 'META-INF/MANIFEST.MF'

    def entry(self, name='assets/test', data=b'test', algo='sha256'):
        return f"Name: {name}\n{'SHA-256' if algo == 'sha256' else 'SHA1'}-Digest: {base64.b64encode(hashlib.new(algo, data).digest()).decode()}\n\n"

    def test_matching_sha256_and_sha1_read_only(self):
        (self.root / 'assets').mkdir()
        (self.root / 'assets/test').write_bytes(b'test')
        (self.root / 'assets/other').write_bytes(b'test')
        self.manifest.write_text(self.entry() + self.entry('assets/other', algo='sha1'))
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        result = audit.verify_manifest(self.root)
        self.assertEqual((result['status'], result['matching']), ('matching', 2))
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_missing_and_different(self):
        (self.root / 'bad').write_bytes(b'')
        self.manifest.write_text(self.entry('bad') + self.entry('missing'))
        result = audit.verify_manifest(self.root)
        self.assertEqual(result['different'], ['bad'])
        self.assertEqual(result['missing'], ['missing'])

    def test_path_traversal_and_absolute_rejected(self):
        for name in ('../secret', '/etc/passwd', 'C:/secret', 'assets\\..\\secret'):
            self.manifest.write_text(self.entry(name))
            self.assertEqual(len(audit.verify_manifest(self.root)['rejected']), 1)

    def test_duplicate_and_invalid_digest_rejected(self):
        self.manifest.write_text(self.entry() * 2)
        self.assertEqual(len(audit.verify_manifest(self.root)['rejected']), 1)
        self.manifest.write_text('Name: bad\nSHA1-Digest: xyz!\n\n')
        self.assertEqual(len(audit.verify_manifest(self.root)['rejected']), 1)

    def test_missing_empty_and_unsupported_manifest_inconclusive(self):
        self.assertEqual(audit.verify_manifest(self.root)['status'], 'unavailable')
        self.manifest.write_text('Manifest-Version: 1.0\n\n')
        self.assertEqual(audit.verify_manifest(self.root)['status'], 'unavailable')
        self.manifest.write_text('Name: file\nUnsupported-Digest: aaa\n\n')
        self.assertEqual(audit.verify_manifest(self.root)['status'], 'partial')

    def test_folded_names(self):
        (self.root / 'long name').write_bytes(b'test')
        self.manifest.write_text(self.entry('long name').replace('long name', 'long\n  name'))
        self.assertEqual(audit.verify_manifest(self.root)['matching'], 1)

    def test_total_limit(self):
        (self.root / 'file').write_bytes(b'test')
        self.manifest.write_text(self.entry('file'))
        with patch.object(audit, 'MAX_TOTAL', 3):
            self.assertEqual(audit.verify_manifest(self.root)['status'], 'mismatch')

    def test_no_fix_promised(self):
        result = audit.audit(self.root)
        self.assertFalse(result['automatic_repair'])
        self.assertIn('não comprova', result['notice'])


if __name__ == '__main__':
    unittest.main()
