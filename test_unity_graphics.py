"""Known-build graphics settings, preservation, refusal and rollback tests."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_unity_egl as fixture
import unity_graphics as graphics
import unity_egl as egl
import repair_port as repair

class UnityGraphicsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.UnityEglTests(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.port, self.launcher, self.args = self.fixture.port, self.fixture.launcher, self.fixture.args
        (self.fixture.root/'PortMaster').mkdir()
        egl.apply(self.args)
        self.config = self.port/'hk.toml'
        self.original = ('[paths]\ngame_files="./gamedata/"\nandroid_files="../conf/"\n'
                         'android_external_files="../conf/"\n[gpu]\n# preserve this\ntextureMaxDim = 1024 # memory\n')
        self.config.write_text(self.original, encoding='utf-8')
        self.prefs = self.port/graphics.PREFS
        self.prefs.parent.mkdir(parents=True)
        self.data = {'ints': {'ShaderQuality': 1, 'NativeInput': 0, 'VidTFR': 400, 'VidVSync': 0, 'VidParticles': 1},
                     'floats': {'MasterVolume': 0.5}, 'strings': {'KeyJump_V2': 'SPACE', 'other': 'preserve'}}
        self.prefs.write_text(json.dumps(self.data), encoding='utf-8')
        self.save = self.port/'conf/user1.dat'; self.save.write_bytes(b'untouched save')

    def test_apply_restore_preserve_every_other_preference(self):
        before = self.prefs.read_bytes()
        graphics.apply(self.args)
        self.assertEqual(graphics.check(self.port,self.launcher)[0],'applied')
        self.assertIn('textureMaxDim = 0 # memory',self.config.read_text())
        data = json.loads(self.prefs.read_bytes()); data['ints']['ShaderQuality']=1
        self.assertEqual(data,self.data)
        self.assertEqual(self.save.read_bytes(),b'untouched save')
        repair.command_restore(self.args)
        self.assertEqual(self.config.read_text(),self.original)
        self.assertEqual(self.prefs.read_bytes(),before)
        self.assertEqual(egl.check(self.port,self.launcher)[0],'applied')

    def test_unknown_build_and_no_egl_refused(self):
        (self.port/'unityloader').write_bytes(b'unknown')
        with self.assertRaises(ValueError): graphics.apply(self.args)
        self.assertEqual(self.config.read_text(),self.original)

    def test_wrong_paths_refused(self):
        self.config.write_text(self.original.replace('../conf/','/somewhere/'))
        self.assertEqual(graphics.check(self.port,self.launcher)[0],'unsupported')

    def test_ambiguous_configs_refused(self):
        for addition in ('textureMaxDim = 512\n', '[gpu]\ntextureMaxDim=0\n'):
            self.config.write_text(self.original+addition)
            self.assertEqual(graphics.check(self.port,self.launcher)[0],'unsupported')

    def test_invalid_or_missing_preferences_refused(self):
        for data in ({'ints': {'ShaderQuality': True}}, {'ints': {'ShaderQuality': 99}}, {}, []):
            self.prefs.write_text(json.dumps(data))
            self.assertEqual(graphics.check(self.port,self.launcher)[0],'unsupported')
        self.prefs.unlink()
        self.assertEqual(graphics.check(self.port,self.launcher)[0],'unsupported')

    def test_running_game_refused(self):
        with patch.object(egl,'running',return_value=True):
            with self.assertRaisesRegex(ValueError,'feche Hollow'): graphics.apply(self.args)

    def test_user_framecap_is_never_changed(self):
        for cap in (30, 60, 120, 400):
            self.data['ints']['VidTFR'] = cap
            self.prefs.write_text(json.dumps(self.data), encoding='utf-8')
            graphics.apply(self.args)
            current=json.loads(self.prefs.read_bytes())
            self.assertEqual(current['ints']['VidTFR'],cap)
            self.assertEqual(current['ints']['VidVSync'],0)
            self.assertEqual(current['ints']['VidParticles'],1)

    def test_automatic_plan_applies_both_repairs(self):
        repair.command_restore(self.args)  # remove only the fixture's EGL repair
        self.args.pm_home=str(self.fixture.root/'PortMaster')
        self.args.architecture=['aarch64']; self.args.runtime=[]
        repair.command_auto_repair(self.args)
        self.assertEqual(egl.check(self.port,self.launcher)[0],'applied')
        self.assertEqual(graphics.check(self.port,self.launcher)[0],'applied')
        self.assertEqual(json.loads(self.prefs.read_bytes())['ints']['VidTFR'],400)
        self.assertEqual(self.save.read_bytes(),b'untouched save')
        repair.command_restore(self.args)
        self.assertEqual(self.config.read_text(),self.original)
        self.assertEqual(egl.check(self.port,self.launcher)[0],'applied')
        repair.command_restore(self.args)
        self.assertEqual(egl.check(self.port,self.launcher)[0],'available')

    def test_automatic_plan_explains_missing_preferences(self):
        repair.command_restore(self.args)
        self.prefs.unlink()
        self.args.pm_home=str(self.fixture.root/'PortMaster')
        self.args.architecture=['aarch64']; self.args.runtime=[]
        import io
        from contextlib import redirect_stdout
        output=io.StringIO()
        with redirect_stdout(output): repair.command_auto_repair(self.args)
        self.assertEqual(egl.check(self.port,self.launcher)[0],'applied')
        self.assertFalse(self.prefs.exists())
        self.assertIn('ajuste gráfico ainda pendente',output.getvalue())

    def test_idempotent_and_preserves_bytes_when_already_configured(self):
        graphics.apply(self.args)
        before = self.config.read_bytes(), self.prefs.read_bytes()
        manifests = list(self.fixture.doctor.rglob('manifest.json'))
        graphics.apply(self.args)
        self.assertEqual(before,(self.config.read_bytes(),self.prefs.read_bytes()))
        self.assertEqual(manifests,list(self.fixture.doctor.rglob('manifest.json')))

    def test_failure_on_second_file_rolls_back_first(self):
        writer = egl.atomic_replace
        def fail(path, data, mode):
            if path == self.prefs: raise OSError('disk failure')
            return writer(path,data,mode)
        with patch.object(egl,'atomic_replace',side_effect=fail):
            with self.assertRaisesRegex(OSError,'disk failure'): graphics.apply(self.args)
        self.assertEqual(self.config.read_text(),self.original)
        self.assertEqual(json.loads(self.prefs.read_bytes()),self.data)

    def test_config_symlink_refused(self):
        outside=self.fixture.root/'outside'; outside.write_text(self.original)
        self.config.unlink()
        try: self.config.symlink_to(outside)
        except OSError: self.skipTest('Windows symlink permission')
        self.assertEqual(graphics.check(self.port,self.launcher)[0],'unsupported')

if __name__ == '__main__': unittest.main()
