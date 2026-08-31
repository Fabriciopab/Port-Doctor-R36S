"""Updater tests: network responses are simulated, filesystem uses owned fixtures."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('updater', ROOT / 'portdoctor/tools/updater.py')
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)


def package(extra=None, version='0.11.0'):
    stream = io.BytesIO()
    contents = {'Port Doctor R36S.sh': '#!/bin/bash\n', 'portdoctor/lovegame/main.lua': '-- next release',
                'portdoctor/lovegame/conf.lua': '-- config', 'portdoctor/portdoctor.gptk': 'back=esc',
                'portdoctor/tools/updater.py': '# source', 'portdoctor/tools/update-install.sh': '#!/bin/bash\n',
                'portdoctor/conf/reports/': '', 'portdoctor/release.json': json.dumps({
                    'app': up.APP, 'version': version, 'update_protocol': 1, 'github_owner': 'Fabriciopab'})}
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
        for name, content in extra or []:
            info = ZipInfo(name)
            info.filename = name  # prevent Windows normalizing the malicious fixture
            info.orig_filename = name
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)
    return stream.getvalue()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='portdoctor-update-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'ports/portdoctor'
        (self.home / 'conf').mkdir(parents=True)
        (self.home / 'tools').mkdir()
        self.manifest = {'app': up.APP, 'version': '0.10.0', 'update_protocol': 1,
                         'github_owner': 'Fabriciopab', 'github_repository': 'Test-Port-Doctor'}
        (self.home / 'release.json').write_text(json.dumps(self.manifest))
        (self.home / 'tools/update-install.sh').write_text('#!/bin/bash\n# trusted local fixture')
        (self.home / 'conf/keep.txt').write_text('user data')
        self.updater = up.Updater(self.home)
        self.payload = package()
        self.hash = hashlib.sha256(self.payload).hexdigest()
        self.release = {'id': 123, 'tag_name': 'v0.11.0', 'draft': False, 'prerelease': False, 'assets': [{
            'name': 'Port-Doctor-R36S-v0.11.0.zip', 'state': 'uploaded', 'size': len(self.payload),
            'digest': 'sha256:' + self.hash,
            'browser_download_url': 'https://github.com/Fabriciopab/Test-Port-Doctor/releases/download/v0.11.0/Port-Doctor-R36S-v0.11.0.zip'}]}

    def zip_path(self, payload=None):
        p = self.root / 'test.zip'
        p.write_bytes(payload or self.payload)
        return p

    def prepare(self, data=None):
        with patch.object(up, 'api_json', return_value=self.release), \
             patch.object(up, 'open_url', return_value=io.BytesIO(self.payload if data is None else data)):
            return self.updater.prepare(123, self.hash)

    def test_version_order(self):
        self.assertGreater(up.version('0.10.0'), up.version('0.9.9'))
        self.assertEqual(up.version('v1.2.3'), (1, 2, 3))
        for invalid in ('1.2', '01.2.3', 'v1.2.3-beta', '../x', '1.2.3;reboot'):
            with self.assertRaises(ValueError): up.version(invalid)

    def test_url_allowlist(self):
        up.safe_url('https://release-assets.githubusercontent.com/x?token=example')
        for url in ('http://github.com/a', 'https://evil.invalid/x', 'https://github.com@evil.invalid/x',
                    'https://user:pass@github.com/x', 'https://github.com:444/x'):
            with self.assertRaises(ValueError): up.safe_url(url)

    def test_no_repository_no_network(self):
        self.updater.manifest['github_repository'] = None
        with patch.object(up, 'api_json') as api:
            result = self.updater.check()
        self.assertEqual(result['kind'], 'text')
        self.assertIn('não configurado', result['title'])
        api.assert_not_called()

    def test_new_release_offer(self):
        with patch.object(up, 'api_json', return_value=self.release):
            result = self.updater.check()
        self.assertEqual(result['kind'], 'offer')
        self.assertEqual(result['offer']['sha256'], self.hash)
        self.assertFalse(self.updater.base.exists())

    def test_old_release_not_offered(self):
        self.release['tag_name'] = 'v0.9.0'
        with patch.object(up, 'api_json', return_value=self.release):
            self.assertEqual(self.updater.check()['kind'], 'text')

    def test_untrusted_assets_refused(self):
        asset = self.release['assets'][0]
        for field, value in [('digest', None), ('browser_download_url', 'https://evil.invalid/next.zip'),
                             ('size', up.MAX_DOWNLOAD + 1), ('name', 'source.zip')]:
            previous = asset.get(field)
            asset[field] = value
            with self.subTest(field=field), patch.object(up, 'api_json', return_value=self.release), self.assertRaises(ValueError):
                self.updater.check()
            asset[field] = previous

    def test_prerelease_refused(self):
        self.release['prerelease'] = True
        with patch.object(up, 'api_json', return_value=self.release), self.assertRaises(ValueError):
            self.updater.check()

    def test_valid_package(self):
        self.assertGreater(up.validate_zip(self.zip_path(), '0.11.0'), 0)

    def test_wrong_version_refused(self):
        with self.assertRaises(ValueError):
            up.validate_zip(self.zip_path(), '0.12.0')

    def test_unsafe_paths_and_conf_refused(self):
        for name in ('../escape', '/etc/shadow', 'portdoctor/../escape', 'portdoctor\\escape',
                     'othergame/save', 'portdoctor/conf/save.txt', 'portdoctor/Conf/save.txt',
                     'portdoctor/space /data', 'portdoctor/a:b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                up.validate_zip(self.zip_path(package([(name, 'bad')])), '0.11.0')

    def test_duplicate_case_refused(self):
        with self.assertRaises(ValueError):
            up.validate_zip(self.zip_path(package([('portdoctor/lovegame/MAIN.lua', 'bad')])), '0.11.0')

    def test_symlink_archive_refused(self):
        stream = io.BytesIO(self.payload)
        with ZipFile(stream, 'a') as archive:
            link = ZipInfo('portdoctor/link')
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, '/etc')
        with self.assertRaises(ValueError):
            up.validate_zip(self.zip_path(stream.getvalue()), '0.11.0')

    def test_zip_bomb_refused(self):
        with self.assertRaises(ValueError):
            up.validate_zip(self.zip_path(package([('portdoctor/bomb', '0' * 2000000)])), '0.11.0')

    def test_prepare_does_not_install(self):
        result = self.prepare()
        self.assertEqual(result['kind'], 'ready')
        stage, data = self.updater.pending()
        self.assertEqual(data['state'], 'ready')
        self.assertEqual((stage / 'install.sh').read_text(), '#!/bin/bash\n# trusted local fixture')
        self.assertEqual(json.loads((self.home / 'release.json').read_text())['version'], '0.10.0')
        self.assertEqual((self.home / 'conf/keep.txt').read_text(), 'user data')

    def test_partial_download_refused(self):
        with self.assertRaises(ValueError): self.prepare(self.payload[:-5])
        self.assertIsNone(self.updater.pending())
        self.assertEqual(list(self.updater.base.glob('[0-9a-f]' * 32)), [])

    def test_digest_changed_refused(self):
        data = bytearray(self.payload); data[30] ^= 1
        with self.assertRaises(ValueError): self.prepare(bytes(data))
        self.assertIsNone(self.updater.pending())

    def test_space_refused_before_download(self):
        from collections import namedtuple
        usage = namedtuple('usage', 'total used free')(1, 1, 0)
        with patch.object(up, 'api_json', return_value=self.release), patch.object(up.shutil, 'disk_usage', return_value=usage), \
             patch.object(up, 'open_url') as download, self.assertRaises(ValueError):
            self.updater.prepare(123, self.hash)
        download.assert_not_called()

    def test_second_prepare_refused(self):
        self.prepare()
        with self.assertRaises(ValueError): self.prepare()

    def test_tampered_stage_not_executed(self):
        self.prepare()
        stage, _ = self.updater.pending()
        (stage / 'install.sh').write_text('tampered')
        with patch.object(up.subprocess, 'run') as run, self.assertRaises(ValueError):
            self.updater.apply()
        run.assert_not_called()

    def test_install_after_prepare(self):
        self.prepare()
        def fake_install(args, **kwargs):
            self.assertEqual(args[0], '/bin/bash')
            self.assertEqual(kwargs['env']['PORTDOCTOR_INSTALL_NO_RESTART'], '1')
            self.assertEqual(kwargs['env']['PORTDOCTOR_INSTALL_VERSION'], '0.11.0')
            self.manifest['version'] = '0.11.0'
            (self.home / 'release.json').write_text(json.dumps(self.manifest))
            return type('Result', (), {'returncode': 0})()
        with patch.object(up.subprocess, 'run', side_effect=fake_install):
            result = self.updater.apply()
        self.assertTrue(result['ok'])
        self.assertIsNone(self.updater.pending())
        self.assertEqual((self.home / 'conf/keep.txt').read_text(), 'user data')

    def test_failed_install_not_retried(self):
        self.prepare()
        with patch.object(up.subprocess, 'run', return_value=type('Result', (), {'returncode': 1})()):
            self.assertFalse(self.updater.apply()['ok'])
        with patch.object(up.subprocess, 'run') as run, self.assertRaises(ValueError):
            self.updater.apply()
        run.assert_not_called()
        self.assertIn('failed', self.updater.status()['text'])

    def test_cancel_preserves_user_data(self):
        self.prepare()
        stage, _ = self.updater.pending()
        self.updater.cancel()
        self.assertIsNone(self.updater.pending())
        self.assertFalse((stage / 'portdoctor.zip').exists())
        self.assertTrue((stage / 'state.json').exists())
        self.assertEqual((self.home / 'conf/keep.txt').read_text(), 'user data')

    def test_repository_config_only_fixed_owner(self):
        for invalid in ('https://github.com/Other/repo', '../outside', 'Other/repo'):
            with self.assertRaises(ValueError): self.updater.configure(invalid)
        with patch.object(up, 'api_json', return_value={'full_name': 'Other/Repo', 'private': False}), self.assertRaises(ValueError):
            self.updater.configure('Repo')
        with patch.object(up, 'api_json', return_value={'full_name': 'Fabriciopab/Repo', 'private': False}):
            self.updater.configure('Repo')
        self.assertEqual(self.updater.repository(), 'Repo')


if __name__ == '__main__':
    unittest.main(verbosity=2)
