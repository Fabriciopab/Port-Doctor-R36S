"""Regression tests for battery writes and truthful post-repair verification."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'portdoctor/tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


battery = load('battery')
repair = load('repair_port')


class BatteryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sys = self.root / 'sys'
        self.state = self.root / 'run/state.json'
        self.light = self.sys / 'class/backlight/panel'
        self.light.mkdir(parents=True)
        (self.light / 'max_brightness').write_text('160')
        (self.light / 'brightness').write_text('80')
        self.cpu = self.sys / 'devices/system/cpu/cpufreq/policy0'
        self.cpu.mkdir(parents=True)
        (self.cpu / 'scaling_governor').write_text('ondemand')
        (self.cpu / 'scaling_available_governors').write_text('ondemand conservative performance')

    def apply(self, action, writer=battery.checked_write):
        return battery.adjust(action, self.sys, self.state, writer)

    def test_apply_idempotent_restore(self):
        self.apply('economy'); self.apply('economy')
        self.assertEqual((self.light / 'brightness').read_text().strip(), '48')
        self.assertEqual((self.cpu / 'scaling_governor').read_text().strip(), 'conservative')
        self.apply('dimmer'); self.apply('restore')
        self.assertEqual((self.light / 'brightness').read_text().strip(), '80')
        self.assertEqual((self.cpu / 'scaling_governor').read_text().strip(), 'ondemand')

    def test_floor_and_ceiling(self):
        for _ in range(15): self.apply('dimmer')
        self.assertEqual((self.light / 'brightness').read_text().strip(), '24')
        for _ in range(15): self.apply('brighter')
        self.assertEqual((self.light / 'brightness').read_text().strip(), '160')

    def test_external_change_preserved(self):
        self.apply('economy')
        (self.light / 'brightness').write_text('90')
        self.apply('restore')
        self.assertEqual((self.light / 'brightness').read_text(), '90')
        with self.assertRaisesRegex(RuntimeError, 'firmware'):
            self.apply('restore')

    def test_partial_failure_rolls_back(self):
        def writer(path, value):
            if str(path).endswith('scaling_governor') and value == 'conservative':
                raise OSError('read-only')
            battery.checked_write(path, value)
        with self.assertRaisesRegex(RuntimeError, 'restaurados'):
            self.apply('economy', writer)
        self.assertEqual((self.light / 'brightness').read_text().strip(), '80')
        self.assertEqual(json.loads(self.state.read_text()), {})

    def test_unknown_hardware_no_write(self):
        self.assertIn('Nenhuma', battery.adjust('economy', self.root / 'missing', self.state))
        self.assertFalse(self.state.exists())

    def test_status_units_and_missing_values(self):
        base = self.sys / 'class/power_supply/battery'
        base.mkdir(parents=True)
        (base / 'uevent').write_text('POWER_SUPPLY_CAPACITY=77\nPOWER_SUPPLY_CURRENT_NOW=-316000\nPOWER_SUPPLY_VOLTAGE_NOW=4052000\nPOWER_SUPPLY_STATUS=Discharging\n')
        text = battery.status(self.sys)
        for expected in ('77%', '-316.00 mA', '4.05 V', '1.28 W', 'Temperatura: não informada'):
            self.assertIn(expected, text)

    def test_untrusted_restore_target_rejected(self):
        self.apply('economy')
        data=json.loads(self.state.read_text())
        data[str(self.light / 'brightness')]['original']='0'
        self.state.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, 'intervalo'):
            self.apply('restore')


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.port=self.root/'hollowknight'; self.port.mkdir()
        self.launcher=self.root/'HollowKnight.sh'; self.launcher.write_text('#!/bin/bash\n')
        self.doctor=self.root/'portdoctor'; self.doctor.mkdir()
        self.log=self.port/'log.txt'; self.log.write_text('old log')
        self.folder,self.manifest=repair.new_backup(self.doctor,self.port,self.launcher,'repair-library')
        self.manifest['library']='libavcodec.so.58'; repair.save_manifest(self.folder,self.manifest)
        self.args=argparse.Namespace(launcher=str(self.launcher),port_home=str(self.port),doctor_home=str(self.doctor))

    def new_log(self,text):
        self.log.write_text(text)
        stamp=int(__import__('time').time()*1e9)+2_000_000_000
        os.utime(self.log,ns=(stamp,stamp)); return stamp

    def test_new_different_crash_fails(self):
        self.new_log('Segmentation fault')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): repair.command_verify(self.args)
        self.assertEqual(json.loads((self.folder/'manifest.json').read_text())['verification'],'failed')

    def test_quiet_log_not_success(self):
        self.new_log('OpenGL initialized')
        with contextlib.redirect_stdout(io.StringIO()): repair.command_verify(self.args)
        self.assertEqual(json.loads((self.folder/'manifest.json').read_text())['verification'],'awaiting_game_test')

    def test_new_tombstone_detected(self):
        stamp=self.new_log('OpenGL initialized')
        crash=self.port/'tombstone_00'; crash.write_text('signal 7 (SIGBUS), code -6 (SI_TKILL)')
        os.utime(crash,ns=(stamp,stamp))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): repair.command_verify(self.args)

    def test_old_bundled_crash_ignored(self):
        crash=self.port/'tombstone_00'; crash.write_text('signal 7 (SIGBUS)')
        os.utime(crash,(100,100)); self.new_log('OpenGL initialized')
        with contextlib.redirect_stdout(io.StringIO()): repair.command_verify(self.args)
        self.assertEqual(json.loads((self.folder/'manifest.json').read_text())['verification'],'awaiting_game_test')

    def test_unchanged_log_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): repair.command_verify(self.args)


if __name__=='__main__': unittest.main()
