import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HELPER = ROOT / "portdoctor/tools/port_hub.py"


class PortHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="port-hub-test-")
        base = Path(self.tmp.name)
        self.share = base / "share"
        self.source = self.share / "R36S-Ports"
        self.destination = base / "roms/ports"
        self.doctor = base / "doctor"
        self.source.mkdir(parents=True)
        self.destination.mkdir(parents=True)
        package = self.source / "Demo Port"
        (package / "demo").mkdir(parents=True)
        (package / "Demo Port.sh").write_text("#!/bin/bash\necho demo\n", encoding="utf-8")
        (package / "demo/game.dat").write_bytes(b"demo-data" * 1024)
        self.env = {**os.environ, "PORTDOCTOR_NETWORK_MOUNT": str(self.share),
                    "PORTDOCTOR_PORTS_ROOTS": str(self.destination), "PORTDOCTOR_HOME": str(self.doctor)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_helper(self, *args):
        process = subprocess.run([sys.executable, str(HELPER), *args], env=self.env, text=True, capture_output=True)
        return process, json.loads(process.stdout)

    def test_list_plan_install_and_refuse_overwrite(self):
        listed, data = self.run_helper("list")
        self.assertEqual(listed.returncode, 0)
        self.assertEqual(data["packages"][0]["id"], "Demo Port")
        planned, plan = self.run_helper("plan", "Demo Port", str(self.destination))
        self.assertEqual(planned.returncode, 0)
        installed, result = self.run_helper("execute", "Demo Port", str(self.destination), plan["token"])
        self.assertEqual(installed.returncode, 0, installed.stderr + installed.stdout)
        launcher = self.destination / "Demo Port.sh"
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher.stat().st_mode & stat.S_IXUSR)
        self.assertEqual((self.destination / "demo/game.dat").read_bytes(), b"demo-data" * 1024)
        refused, response = self.run_helper("plan", "Demo Port", str(self.destination))
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(response["title"], "Port já existente")

    def test_refuses_symlink_and_expired_plan(self):
        package = self.source / "Linked"
        package.mkdir()
        (package / "Linked.sh").write_text("#!/bin/bash\n", encoding="utf-8")
        (package / "outside").symlink_to(self.share)
        _, listed = self.run_helper("list")
        self.assertNotIn("Linked", [item["id"] for item in listed["packages"]])
        _, plan = self.run_helper("plan", "Demo Port", str(self.destination))
        (self.source / "Demo Port/demo/new.dat").write_bytes(b"changed")
        expired, response = self.run_helper("execute", "Demo Port", str(self.destination), plan["token"])
        self.assertNotEqual(expired.returncode, 0)
        self.assertEqual(response["title"], "Plano expirado")


if __name__ == "__main__":
    unittest.main()
