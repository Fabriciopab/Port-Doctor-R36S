"""Destructive-operation tests run only in disposable fixtures, never real ROMs."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'portdoctor/tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fm = load('file_manager')
network = load('network_status')


class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='portdoctor-v090-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'roms'
        self.ports = self.root / 'ports'
        self.game = self.ports / 'example'
        self.game.mkdir(parents=True)
        self.doctor = self.ports / 'portdoctor'
        self.doctor.mkdir()
        self.source = self.game / 'data.txt'
        self.source.write_text('conteúdo teste')
        self.manager = fm.Manager([self.root], self.doctor, self.base / 'proc')

    def plan(self, operation, **kwargs):
        return self.manager.plan({'operation': operation, **{k: str(v) for k, v in kwargs.items()}})

    def execute(self, plan):
        return self.manager.execute(plan['root'], plan['token'])

    def trash(self):
        return Path(self.manager.trash_items()['items'][0]['path'])

    def test_list_and_info(self):
        result = self.manager.listing(str(self.game))
        self.assertEqual(result['items'][0]['name'], 'data.txt')
        self.assertIn('itens', self.manager.request({'action': 'info', 'path': str(self.game)})['text'])

    def test_delete_restore(self):
        plan = self.plan('delete', path=self.game)
        self.assertTrue(self.source.exists(), 'Preview must not remove data')
        self.execute(plan)
        self.assertFalse(self.game.exists())
        self.execute(self.plan('restore', path=self.trash()))
        self.assertEqual(self.source.read_text(), 'conteúdo teste')

    def test_purge(self):
        self.execute(self.plan('delete', path=self.source))
        trash = self.trash()
        plan = self.plan('purge', path=trash)
        self.assertTrue(plan['permanent'])
        self.execute(plan)
        self.assertFalse(trash.exists())
        self.assertTrue(self.game.exists())

    def test_empty_trash_all(self):
        second = self.game / 'second.txt'
        second.write_text('second')
        self.execute(self.plan('delete', path=self.source))
        self.execute(self.plan('delete', path=second))
        self.assertEqual(len(self.manager.trash_items()['items']), 2)
        plan = self.plan('purge_all')
        self.assertTrue(plan['permanent'])
        self.execute(plan)
        self.assertEqual(self.manager.trash_items()['items'], [])

    def test_purge_failure_retains_recovery_journal(self):
        self.execute(self.plan('delete', path=self.game))
        trash = self.trash()
        plan = self.plan('purge', path=trash)
        with patch.object(fm.shutil, 'rmtree', side_effect=OSError('fixture IO error')), self.assertRaises(ValueError):
            self.execute(plan)
        self.assertTrue((trash / 'manifest.json').exists())
        self.assertEqual(len(self.manager.trash_items()['items']), 1)
        self.execute(self.plan('restore', path=trash))
        self.assertTrue(self.source.exists())

    def test_copy_verified_and_original_preserved(self):
        target = self.ports / 'destino'
        target.mkdir()
        self.execute(self.plan('copy', path=self.game, destination=target))
        self.assertEqual((target / 'example/data.txt').read_bytes(), self.source.read_bytes())

    def test_cut_and_rename(self):
        target = self.ports / 'destino'
        target.mkdir()
        self.execute(self.plan('move', path=self.source, destination=target))
        new = target / self.source.name
        self.assertFalse(self.source.exists())
        self.execute(self.plan('rename', path=new, destination=target, name='ação do jogo.txt'))
        self.assertTrue((target / 'ação do jogo.txt').exists())

    def test_mkdir(self):
        self.execute(self.plan('mkdir', destination=self.game, name='Meus arquivos'))
        self.assertTrue((self.game / 'Meus arquivos').is_dir())

    @unittest.skipUnless(os.name == 'posix', 'Linux legacy filesystem fallback')
    def test_legacy_reservation_no_overwrite(self):
        destination = self.game / 'new.txt'
        fm.reserved_rename(self.source, destination)
        self.assertTrue(destination.exists())
        self.source.write_text('second')
        with self.assertRaises(FileExistsError):
            fm.reserved_rename(self.source, destination)
        self.assertEqual(destination.read_text(), 'conteúdo teste')
        self.assertEqual(self.source.read_text(), 'second')

    @unittest.skipUnless(os.name == 'posix', 'Linux legacy filesystem fallback')
    def test_legacy_directory_reservation(self):
        destination = self.ports / 'renamed'
        fm.reserved_rename(self.game, destination)
        self.assertTrue((destination / 'data.txt').exists())

    def test_legacy_failure_removes_only_empty_reservation(self):
        destination = self.game / 'new.txt'
        with patch.object(fm.os, 'rename', side_effect=OSError('fixture')), self.assertRaises(OSError):
            fm.reserved_rename(self.source, destination)
        self.assertTrue(self.source.exists())
        self.assertFalse(destination.exists())

    def test_protected_paths(self):
        for path in [self.root, self.ports, self.doctor, self.base, self.root / '..' / 'outside']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.plan('delete', path=path)
        bios = self.root / 'bios'
        bios.mkdir()
        (bios / 'file.bin').touch()
        with self.assertRaises(ValueError):
            self.plan('delete', path=bios / 'file.bin')

    def test_cannot_copy_inside_itself(self):
        with self.assertRaises(ValueError):
            self.plan('copy', path=self.game, destination=self.game)

    def test_collision_before_and_after_preview(self):
        target = self.ports / 'other'
        target.mkdir()
        plan = self.plan('copy', path=self.source, destination=target)
        (target / self.source.name).write_text('existing')
        with self.assertRaises(ValueError):
            self.execute(plan)
        self.assertEqual((target / self.source.name).read_text(), 'existing')
        with self.assertRaises(ValueError):
            self.plan('move', path=self.source, destination=target)

    def test_stale_plan(self):
        plan = self.plan('delete', path=self.game)
        self.source.write_text('changed after preview')
        with self.assertRaises(ValueError):
            self.execute(plan)
        self.assertTrue(self.source.exists())

    def test_token_cannot_replay(self):
        plan = self.plan('delete', path=self.source)
        self.execute(plan)
        with self.assertRaises(ValueError):
            self.execute(plan)

    def test_expired_plan(self):
        plan = self.plan('delete', path=self.source)
        with patch.object(fm.time, 'time', return_value=time.time() + 1000), self.assertRaises(ValueError):
            self.execute(plan)

    def test_restore_collision_preserves_new_file(self):
        self.execute(self.plan('delete', path=self.source))
        self.source.write_text('new content')
        with self.assertRaises(ValueError):
            self.plan('restore', path=self.trash())
        self.assertEqual(self.source.read_text(), 'new content')

    def launcher(self):
        script = self.ports / 'Example Game.sh'
        script.write_text('#!/bin/bash\nGAMEDIR="/$directory/ports/example"\n')
        (self.game / 'port.json').write_text(json.dumps({'items': ['Example Game.sh', 'example']}))
        return script

    def test_uninstall_and_recover_saves(self):
        launcher = self.launcher()
        (self.game / 'save.dat').write_text('saved progress')
        plan = self.plan('uninstall', path=self.game)
        self.assertIn('INCLUSIVE saves', plan['text'])
        self.execute(plan)
        self.assertFalse(launcher.exists())
        self.assertFalse(self.game.exists())
        self.execute(self.plan('restore', path=self.trash()))
        self.assertTrue(launcher.exists())
        self.assertEqual((self.game / 'save.dat').read_text(), 'saved progress')

    def test_unknown_launcher_refused(self):
        with self.assertRaises(ValueError):
            self.plan('uninstall', path=self.game)

    def test_shared_launcher_refused(self):
        self.launcher()
        other = self.ports / 'other'
        other.mkdir()
        (other / 'port.json').write_text(json.dumps({'items': ['other', 'Example Game.sh']}))
        with self.assertRaises(ValueError):
            self.plan('uninstall', path=self.game)

    def test_partial_uninstall_rolls_back(self):
        launcher = self.launcher()
        plan = self.plan('uninstall', path=self.game)
        original = fm.rename_new
        calls = []
        def fail_second(src, dst):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('fixture failure')
            return original(src, dst)
        with patch.object(fm, 'rename_new', side_effect=fail_second), self.assertRaises(ValueError):
            self.execute(plan)
        self.assertTrue(launcher.exists())
        self.assertTrue(self.source.exists())

    def test_cleanup_allowlist_and_age(self):
        save = self.game / 'save.tmp'
        save.write_text('DO NOT DELETE')
        fake = self.game / 'Thumbs.db'
        fake.write_bytes(b'not a real metadata file')
        old = time.time() - 40 * 86400
        os.utime(fake, (old, old))
        self.assertEqual(self.manager.cleanup_candidates(), [])
        fake.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'fixture')
        os.utime(fake, (old, old))
        (self.game / 'tombstone_01').write_text('*** *** ***\nABI: arm64\nold crash')
        os.utime(self.game / 'tombstone_01', (old, old))
        (self.game / 'tombstone_02').write_text('*** *** ***\nABI: arm64\nnew crash')
        plan = self.plan('cleanup')
        self.execute(plan)
        self.assertFalse(fake.exists())
        self.assertFalse((self.game / 'tombstone_01').exists())
        self.assertTrue((self.game / 'tombstone_02').exists())
        self.assertTrue(save.exists())

    def test_mount_refused(self):
        self.manager.mounts.add(self.game)
        with self.assertRaises(ValueError):
            self.plan('delete', path=self.game)

    @unittest.skipUnless(os.name == 'posix', 'Linux symlink fixtures')
    def test_symlink_no_follow(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('keep')
        link = self.game / 'link'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Filesystem does not support symlinks (exFAT)')
        with self.assertRaises(ValueError):
            self.manager.listing(str(link))
        with self.assertRaises(ValueError):
            self.plan('copy', path=self.game, destination=self.ports)
        self.execute(self.plan('delete', path=self.game))
        self.execute(self.plan('purge', path=self.trash()))
        self.assertEqual((outside / 'keep').read_text(), 'keep')

    @unittest.skipUnless(os.name == 'posix', 'Linux process fixtures')
    def test_running_port_refused(self):
        process = self.base / 'proc/123'
        process.mkdir(parents=True)
        try:
            (process / 'cwd').symlink_to(self.game)
        except OSError:
            self.skipTest('Filesystem does not support symlinks (exFAT)')
        with self.assertRaises(ValueError):
            self.plan('delete', path=self.game)


class Network(unittest.TestCase):
    def test_unsupported_no_write(self):
        with patch.object(network, 'nm_active', return_value=False), patch.object(network, 'run') as run:
            with self.assertRaises(ValueError):
                network.toggle(True)
            run.assert_not_called()

    def test_radio_only_verified(self):
        with patch.object(network, 'nm_active', return_value=True), patch.object(network, 'status', return_value='status'), \
             patch.object(network, 'run', side_effect=[('', 0, ''), ('disabled', 0, '')]) as run:
            self.assertIn('desabilitado', network.toggle(False))
            self.assertEqual(run.call_args_list[0].args[0], ['nmcli', '--wait', '10', 'radio', 'wifi', 'off'])
            self.assertEqual(run.call_args_list[1].args[0], ['nmcli', 'radio', 'wifi'])

    def test_radio_failure_not_success(self):
        with patch.object(network, 'nm_active', return_value=True), patch.object(network, 'run', return_value=('', 1, 'permission')):
            with self.assertRaises(ValueError):
                network.toggle(True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
