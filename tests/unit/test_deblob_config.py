from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omarchy_setup.modules.deblob import DeblobError, load_config


class DeblobConfigTests(unittest.TestCase):
    def write_config(self, text: str) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "deblob.toml"
        path.write_text(text)
        return path

    def test_loads_explicit_remove_and_protected_lists(self) -> None:
        config = load_config(
            self.write_config(
                'schema_version = 1\n[packages]\nremove = ["demo-app"]\nprotected = ["base"]\n'
            )
        )

        self.assertEqual(config.remove, ("demo-app",))
        self.assertEqual(config.protected, frozenset({"base"}))

    def test_rejects_remove_and_protected_overlap(self) -> None:
        path = self.write_config(
            'schema_version = 1\n[packages]\nremove = ["base"]\nprotected = ["base"]\n'
        )

        with self.assertRaisesRegex(DeblobError, "both removed and protected"):
            load_config(path)

    def test_rejects_invalid_package_names(self) -> None:
        path = self.write_config(
            'schema_version = 1\n[packages]\nremove = ["bad package"]\nprotected = []\n'
        )

        with self.assertRaisesRegex(DeblobError, "invalid package names"):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
