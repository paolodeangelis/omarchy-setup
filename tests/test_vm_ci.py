"""Pure CI planning/adapter tests; never boot or mutate the host."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import json
import os
import subprocess
import sys
import tempfile


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "vm" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class VmCiTests(unittest.TestCase):
    def setUp(self):
        self.resolve = module("resolve")
        self.host = module("host")
        self.config = {"baseline": "4.0.4", "harness_commit": "reviewed"}

    def test_pinned_does_not_follow_latest(self):
        plan = self.resolve.plan(self.config, "pinned", "v9.0.0")
        self.assertEqual(plan["install_version"], "4.0.4")
        self.assertTrue(plan["run"])

    def test_candidate_skips_equal_and_older(self):
        for mode in ("latest", "upgrade"):
            for version in ("v4.0.4", "v4.0.3"):
                self.assertFalse(self.resolve.plan(self.config, mode, version)["run"])

    def test_upgrade_installs_baseline_latest_installs_candidate(self):
        for mode, expected in (("upgrade", "4.0.4"), ("latest", "4.0.10")):
            plan = self.resolve.plan(self.config, mode, "v4.0.10")
            self.assertTrue(plan["run"])
            self.assertEqual(plan["install_version"], expected)

    def test_reject_unstable_and_shell_input(self):
        for value in ("4.0.4-1", "4.1.0-rc1", "latest", "4.0.4;true", ""):
            with self.assertRaises(ValueError):
                self.resolve.version(value)

    def test_adapter_requires_exactly_one_reviewed_anchor(self):
        for text in ("", "anchor anchor"):
            with self.assertRaises(RuntimeError):
                self.host.replace_once(text, "anchor", "replacement")
        self.assertEqual(self.host.replace_once("anchor", "anchor", "new"), "new")

    def test_reject_unknown_mode(self):
        with self.assertRaises(ValueError):
            self.resolve.plan(self.config, "typo", "v4.0.5")

    def test_cli_skip_does_not_fetch_iso(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release.json"
            with patch.object(sys, "argv", ["resolve", "latest", "--output", str(output)]), \
                    patch.object(self.resolve, "fetch", return_value='{"tag_name":"v4.0.4"}') as fetch, \
                    patch.dict(os.environ, {"GITHUB_OUTPUT": str(Path(directory) / "outputs")}):
                self.resolve.main()
            self.assertFalse(json.loads(output.read_text())["run"])
            fetch.assert_called_once()

    def test_cli_bad_checksum_never_writes_success(self):
        for checksum in ("", "bad", "0" * 64):
            with self.subTest(checksum=checksum), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "release.json"
                with patch.object(sys, "argv", ["resolve", "pinned", "--output", str(output)]), \
                        patch.object(self.resolve, "fetch", return_value=checksum), \
                        self.assertRaises(ValueError):
                    self.resolve.main()
                self.assertFalse(output.exists())

    def test_harness_adapter_keeps_disk_and_tar_without_tty(self):
        fixture = '''omarchy-pkg-add qemu-full edk2-ovmf socat imagemagick tesseract tesseract-data-eng
ssh_guest "OMARCHY_PATH=/usr/share/omarchy OMARCHY_ACCEPTANCE_DIR=/tmp/omarchy-acceptance"
  log "Collecting artifacts into $RUN_DIR"
ssh_guest "tar -cf - /tmp/omarchy-acceptance"
'''
        for upgrade in (False, True):
            adapted = self.host.adapt_harness(fixture, upgrade)
            subprocess.run(["bash", "-n"], input=adapted, text=True, check=True)
            self.assertNotIn("omarchy-pkg-add", adapted)
            self.assertIn('ssh_guest -tt "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=', adapted)
            self.assertIn('ssh_guest "tar ', adapted)
            self.assertEqual('start_vm "$RUN_DIR/run.qcow2"' in adapted, upgrade)

    def test_harness_adapter_supports_ubuntu_firmware_and_imagemagick(self):
        fixture = '''omarchy-pkg-add qemu-full edk2-ovmf socat imagemagick tesseract tesseract-data-eng
OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
OVMF_VARS_TEMPLATE="/usr/share/edk2/x64/OVMF_VARS.4m.fd"
  magick "$shot" out.png
  magick "$shot" gray.png
ssh_guest "OMARCHY_PATH=/usr/share/omarchy OMARCHY_ACCEPTANCE_DIR=/tmp/omarchy-acceptance"
  log "Collecting artifacts into $RUN_DIR"
'''
        adapted = self.host.adapt_harness(
            fixture, False, "/usr/share/OVMF/OVMF_CODE_4M.fd",
            "/usr/share/OVMF/OVMF_VARS_4M.fd", "convert",
        )
        self.assertIn('OVMF_CODE="/usr/share/OVMF/OVMF_CODE_4M.fd"', adapted)
        self.assertIn('OVMF_VARS_TEMPLATE="/usr/share/OVMF/OVMF_VARS_4M.fd"', adapted)
        self.assertEqual(adapted.count("  convert "), 2)

    def test_host_refuses_workstation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_script = root / "tests/vm/host.py"
            plan = root / "release.json"
            plan.write_text('{}')
            with patch.object(self.host, "__file__", str(fake_script)), \
                    patch.object(sys, "argv", ["host", str(plan)]), \
                    patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                    patch.object(self.host, "run") as run, \
                    self.assertRaisesRegex(RuntimeError, "never run on the workstation"):
                self.host.main()
            run.assert_not_called()

    def test_desktop_log_requires_evidence_and_rejects_qml_errors(self):
        desktop = module("desktop")
        for log in ("", "-- No entries --\n", "Cannot assign to non-existent property barMargins", "TypeError: undefined"):
            with self.subTest(log=log), self.assertRaises(RuntimeError):
                desktop.validate_log(log)
        desktop.validate_log("Shell configuration loaded")
