"""Pure CI planning/adapter tests; never boot or mutate the host."""
import importlib.util
from pathlib import Path
import unittest


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
