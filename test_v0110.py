"""No real sysfs, swap, user-account or firewall changes in these tests."""
import importlib.util
import json
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'portdoctor/tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
battery, memory = load('battery'), load('memory')
MIB = memory.MIB

class Fake:
    def __init__(self):
        self.items = {'zram0': self.item(0)}
        self.free = 700 * MIB
        self.calls = []
        self.fail = None
    @staticmethod
    def item(size, active=False, used=0):
        return dict(size=size, active=active, used=used, mounted=False, algorithm='[lzo]', memory_used=0)
    def memory(self): return 900 * MIB, self.free
    def support(self): return True
    def devices(self): return {k: dict(v) for k, v in self.items.items()}
    def create(self): self.calls.append('create'); self.items['zram1'] = self.item(0); return 'zram1'
    def initialize(self, name, size): self.calls.append('initialize'); self.items[name]['size'] = size
    def activate(self, name):
        self.calls.append('activate')
        if self.fail == 'activate': raise OSError('failed')
        self.items[name]['active'] = True
    def deactivate(self, name):
        self.calls.append('deactivate')
        if self.fail == 'deactivate': raise OSError('failed')
        self.items[name]['active'] = False
    def remove(self, name): self.calls.append('remove'); del self.items[name]

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.fake = Fake(); self.module = memory.Memory(self.fake, self.path)
    def test_status_does_not_create(self):
        self.assertIn('450 MiB', self.module.status()); self.assertEqual(self.fake.calls, [])
    def test_percentages(self):
        for p, expected in [(25,225),(50,450),(75,675)]: self.assertEqual(memory.Memory.size(p, 900*MIB), expected*MIB)
        for p in (0,100,150,-1):
            with self.assertRaises(RuntimeError): memory.Memory.size(p, 900*MIB)
    def test_apply_and_restore(self):
        self.module.apply(50)
        self.assertEqual(self.fake.items['zram1']['size'],450*MIB)
        self.assertTrue(self.fake.items['zram1']['active']); self.assertTrue(self.path.exists())
        self.module.remove_owned(); self.assertEqual(list(self.fake.items), ['zram0']); self.assertFalse(self.path.exists())
    def test_apply_idempotent(self):
        self.module.apply(50); self.fake.calls=[]; self.module.apply(50); self.assertEqual(self.fake.calls, [])
    def test_firmware_active_never_touched(self):
        self.fake.items['zram0']=Fake.item(400*MIB,True)
        with self.assertRaisesRegex(RuntimeError,'firmware'): self.module.apply(50)
        self.assertEqual(self.fake.calls, [])
    def test_firmware_inactive_data_never_formatted(self):
        self.fake.items['zram0']=Fake.item(400*MIB)
        with self.assertRaises(RuntimeError): self.module.apply(50)
        self.assertEqual(self.fake.calls, [])
    def test_low_memory_refuses(self):
        self.fake.free=100*MIB
        with self.assertRaises(RuntimeError): self.module.apply(25)
        self.assertEqual(self.fake.calls, [])
    def test_swap_pages_refuse_resize(self):
        self.module.apply(25); self.fake.calls=[]; self.fake.items['zram1']['used']=4096
        with self.assertRaisesRegex(RuntimeError,'uso'): self.module.apply(50)
        self.assertEqual(self.fake.calls, []); self.assertTrue(self.fake.items['zram1']['active'])
    def test_swap_pages_refuse_remove(self):
        self.module.apply(25); self.fake.calls=[]; self.fake.items['zram1']['used']=4096
        with self.assertRaises(RuntimeError): self.module.remove_owned()
        self.assertEqual(self.fake.calls, [])
    def test_changed_device_refused(self):
        self.module.apply(25); self.fake.calls=[]; self.fake.items['zram1']['size']=800*MIB
        with self.assertRaises(RuntimeError): self.module.remove_owned()
        self.assertEqual(self.fake.calls, [])
    def test_failed_swapoff_never_reset(self):
        self.module.apply(25); self.fake.calls=[]; self.fake.fail='deactivate'
        with self.assertRaises(OSError): self.module.remove_owned()
        self.assertNotIn('remove',self.fake.calls); self.assertTrue(self.path.exists())
    def test_failed_activation_journal_kept(self):
        self.fake.fail='activate'
        with self.assertRaises(RuntimeError): self.module.apply(25)
        self.assertTrue(self.path.exists()); self.assertNotIn('remove',self.fake.calls)
        self.fake.fail=None; self.module.remove_owned(); self.assertFalse(self.path.exists())
    def test_resize_empty_owned(self):
        self.module.apply(25); self.module.apply(75); self.assertEqual(self.fake.items['zram1']['size'],675*MIB)
    def test_untrusted_device_name(self):
        self.path.write_text(json.dumps({'device':'../../sda','size':1}))
        with self.assertRaises(RuntimeError): self.module.remove_owned()
        self.assertEqual(self.fake.calls, [])

class ProfilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.state=self.root/'run/state.json'
        self.cpu=self.root/'devices/system/cpu/cpufreq/policy0'; self.cpu.mkdir(parents=True)
        for name,value in {'scaling_governor':'ondemand','scaling_available_governors':'ondemand conservative performance',
                           'scaling_max_freq':'1512000','scaling_min_freq':'1008000'}.items(): (self.cpu/name).write_text(value)
        path=self.root/'firmware/devicetree/base'; path.mkdir(parents=True); (path/'compatible').write_text('rockchip,rk3326\x00')
        self.thermal=self.root/'class/thermal/thermal_zone0'; self.thermal.mkdir(parents=True); (self.thermal/'temp').write_text('53000')
    def apply(self,name): return battery.adjust(name,self.root,self.state)
    def test_performance_does_not_raise_clock(self):
        self.apply('performance'); self.assertEqual((self.cpu/'scaling_governor').read_text().strip(),'performance')
        self.assertEqual((self.cpu/'scaling_max_freq').read_text(),'1512000')
        self.assertEqual((self.cpu/'scaling_min_freq').read_text(),'1008000')
        self.apply('restore'); self.assertEqual((self.cpu/'scaling_governor').read_text().strip(),'ondemand')
    def test_balanced_after_economy(self):
        self.apply('economy'); self.apply('balanced'); self.assertEqual((self.cpu/'scaling_governor').read_text().strip(),'ondemand')
    def test_hot_blocked(self):
        (self.thermal/'temp').write_text('65000')
        with self.assertRaisesRegex(RuntimeError,'65'): self.apply('performance')
        self.assertFalse(self.state.exists())
    def test_no_thermal_blocked(self):
        (self.thermal/'temp').unlink()
        with self.assertRaises(RuntimeError): self.apply('performance')
    def test_higher_clock_blocked(self):
        (self.cpu/'scaling_max_freq').write_text('1800000')
        with self.assertRaises(RuntimeError): self.apply('performance')
        self.assertEqual((self.cpu/'scaling_max_freq').read_text(),'1800000')
    def test_unknown_soc_blocked(self):
        (self.root/'firmware/devicetree/base/compatible').write_text('unknown')
        with self.assertRaises(RuntimeError): self.apply('performance')
    def test_low_battery_blocked(self):
        b=self.root/'class/power_supply/battery'; b.mkdir(parents=True)
        (b/'type').write_text('Battery'); (b/'capacity').write_text('10')
        with self.assertRaises(RuntimeError): self.apply('performance')
    def test_unknown_profile_blocked(self):
        with self.assertRaises(RuntimeError): self.apply('overclock')

class KernelBusyTests(unittest.TestCase):
    def test_retry_only_busy_and_never_active(self):
        backend=memory.Linux()
        current=Fake.item(0)
        with patch.object(backend,'devices',return_value={'zram1':current}), patch.object(backend,'device'), \
             patch.object(backend,'write',side_effect=[OSError(errno.EBUSY,'busy'),None]) as write, \
             patch.object(backend,'remove_id') as remove, patch.object(memory.time,'sleep'):
            backend.remove('zram1'); self.assertEqual(write.call_count,2); remove.assert_called_once()
        current['active']=True
        with patch.object(backend,'devices',return_value={'zram1':current}), patch.object(backend,'write') as write:
            with self.assertRaises(RuntimeError): backend.remove('zram1')
            write.assert_not_called()

    def test_permission_error_not_retried(self):
        backend=memory.Linux()
        with patch.object(backend,'devices',return_value={'zram1':Fake.item(0)}), patch.object(backend,'device'), \
             patch.object(backend,'write',side_effect=OSError(errno.EACCES,'denied')) as write:
            with self.assertRaises(OSError): backend.remove('zram1')
            self.assertEqual(write.call_count,1)

if __name__=='__main__': unittest.main(verbosity=2)
