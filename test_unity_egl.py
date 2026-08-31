"""Recipe safety, persistence, rollback and integrity tests (no real game needed)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'portdoctor/tools'))
import unity_egl as egl
import repair_port as repair

class UnityEglTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.port = self.root/'hollowknight'; self.port.mkdir()
        self.doctor = self.root/'portdoctor'; self.doctor.mkdir()
        self.launcher = self.root/'HollowKnight.sh'
        self.original = '#!/bin/bash\nGAMEDIR="/roms/ports/hollowknight"\n"$GAMEDIR/unityloader" hk.toml &\nwait "$!"\n'
        self.launcher.write_text(self.original, encoding='utf-8')
        self.args = argparse.Namespace(port_home=str(self.port), launcher=str(self.launcher), doctor_home=str(self.doctor))
        self.hashes = {}
        for name in egl.KNOWN:
            path = self.port/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode()); self.hashes[name] = egl.digest(path)
        self.module = self.doctor/'libexec/aarch64/unity-egl-rebind.so'
        self.module.parent.mkdir(parents=True); self.module.write_bytes(b'test module only')
        self.module_sha = egl.digest(self.module)
        for target, value in [('KNOWN',self.hashes),('MODULE_SHA256',self.module_sha)]:
            p = patch.object(egl,target,value); p.start(); self.addCleanup(p.stop)
        for target, value in [('platform_reason',''),('running',False)]:
            p = patch.object(egl,target,return_value=value); p.start(); self.addCleanup(p.stop)
        # Syntax is also tested with real bash in the device integration test.
        p = patch.object(egl.subprocess,'run',return_value=argparse.Namespace(returncode=0,stdout='',stderr=''))
        p.start(); self.addCleanup(p.stop)

    def test_apply_restore_and_saves_unchanged(self):
        saves=self.port/'conf'; saves.mkdir(); (saves/'user1.dat').write_bytes(b'user save')
        before={name:(self.port/name).read_bytes() for name in self.hashes}
        egl.apply(self.args)
        self.assertEqual(egl.check(self.port,self.launcher)[0],'applied')
        self.assertIn('env LD_AUDIT=',self.launcher.read_text(encoding='utf-8'))
        self.assertIn('sha256sum --check --status',self.launcher.read_text(encoding='utf-8'))
        self.assertEqual((self.port/'conf/user1.dat').read_bytes(),b'user save')
        self.assertEqual(before,{name:(self.port/name).read_bytes() for name in self.hashes})
        repair.command_restore(self.args)
        self.assertEqual(self.launcher.read_text(encoding='utf-8'),self.original)
        self.assertFalse((self.port/egl.DESTINATION).exists())

    def test_unknown_build_refused_without_writes(self):
        (self.port/'unityloader').write_bytes(b'different')
        with self.assertRaisesRegex(ValueError,'build validado'): egl.apply(self.args)
        self.assertEqual(self.launcher.read_text(encoding='utf-8'),self.original)
        self.assertFalse((self.doctor/'conf').exists())

    def test_incompatible_device_refused(self):
        with patch.object(egl,'platform_reason',return_value='não é RK3326'):
            self.assertEqual(egl.check(self.port)[0],'unsupported')

    def test_corrupt_module_refused(self):
        self.module.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'módulo'): egl.apply(self.args)
        self.assertFalse((self.doctor/'conf').exists())

    def test_running_game_refused(self):
        with patch.object(egl,'running',return_value=True):
            with self.assertRaisesRegex(ValueError,'feche Hollow'): egl.apply(self.args)

    def test_idempotent(self):
        egl.apply(self.args)
        before=self.launcher.read_bytes()
        egl.apply(self.args)
        self.assertEqual(before,self.launcher.read_bytes())
        self.assertEqual(len(list((self.doctor/'conf').rglob('manifest.json'))),1)

    def test_unrecognized_or_multiple_launches_refused(self):
        for text in ('exec "$GAMEDIR/unityloader" hk.toml','./unityloader hk.toml\n./unityloader hk.toml','LD_AUDIT=x\n./unityloader hk.toml'):
            with self.assertRaises(ValueError): egl.patch_launcher(text)

    def test_preexisting_destination_not_overwritten(self):
        destination=self.port/egl.DESTINATION;destination.parent.mkdir();destination.write_bytes(b'user data')
        with self.assertRaisesRegex(ValueError,'sobrescrito'): egl.apply(self.args)
        self.assertEqual(destination.read_bytes(),b'user data')

    def test_failed_write_rolls_back(self):
        original_write=egl.atomic_replace
        def fail_launcher(path,data,mode):
            if path==self.launcher: raise OSError('disk failure')
            return original_write(path,data,mode)
        with patch.object(egl,'atomic_replace',side_effect=fail_launcher):
            with self.assertRaises(OSError): egl.apply(self.args)
        self.assertEqual(self.launcher.read_text(encoding='utf-8'),self.original)
        self.assertFalse((self.port/egl.DESTINATION).exists())
        manifest=json.loads(next((self.doctor/'conf').rglob('manifest.json')).read_text(encoding='utf-8'))
        self.assertTrue(manifest['restored'])

    def test_symlink_rejected(self):
        target=self.port/'unityloader'; target.unlink()
        outside=self.root/'other'; outside.write_bytes(b'unityloader')
        try: target.symlink_to(outside)
        except OSError: self.skipTest('symlinks require permission on Windows')
        with self.assertRaises(ValueError): egl.local_file(self.port,'unityloader')

    def test_bundled_module_hash(self):
        # This test validates the real bundled binary independently of fixture hashes.
        root=Path(__file__).parent/'portdoctor'
        path=root/'libexec/aarch64/unity-egl-rebind.so'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '7468735542e37a02339326a6e7a43e65b752bd04863df910c13b4d0d4b9be33d')

if __name__=='__main__': unittest.main()
