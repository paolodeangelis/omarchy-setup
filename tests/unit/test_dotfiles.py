from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from omarchy_setup.modules.dotfiles import (
    DotfilesPaths,
    OmarchyDotfilesBackend,
    run_dotfiles,
)
from omarchy_setup.modules.dotfiles.core import HYPR_START, TMUX_START, _replace_block


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def check(self, paths) -> None: self.calls.append("check")
    def install_plugins(self, paths) -> None: self.calls.append("install")
    def apply(self, paths) -> None: self.calls.append("apply")
    def verify(self, paths) -> None: self.calls.append("verify")


class DotfilesTests(unittest.TestCase):
    def test_managed_block_is_idempotent_and_preserves_other_content(self) -> None:
        first = _replace_block("# personal\n", "# start", "# end", "# start\nnew\n# end")
        second = _replace_block(first, "# start", "# end", "# start\nnew\n# end")
        self.assertEqual(first, second)
        self.assertIn("# personal", second)

    def test_apply_runs_complete_lifecycle(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = DotfilesPaths(root, root / "state", root / "config")
            result = run_dotfiles(
                paths=paths, backend=backend, assume_yes=True, dry_run=False,
                stdin=io.StringIO(), stdout=io.StringIO(), progress=False,
            )
        self.assertEqual(result, 0)
        self.assertEqual(backend.calls, ["check", "install", "apply", "verify"])

    def test_apply_preserves_existing_configs_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = DotfilesPaths(root, root / "state", root / "config")
            paths.tmux_config.parent.mkdir(parents=True)
            paths.hypr_bindings.parent.mkdir(parents=True)
            paths.tmux_config.write_text("set -g mouse on\n")
            paths.hypr_bindings.write_text("-- personal\n")
            backend = OmarchyDotfilesBackend()

            backend.apply(paths)
            first_tmux = paths.tmux_config.read_text()
            first_hypr = paths.hypr_bindings.read_text()
            backend.apply(paths)

            self.assertEqual(paths.tmux_config.read_text(), first_tmux)
            self.assertEqual(paths.hypr_bindings.read_text(), first_hypr)
            self.assertIn("set -g mouse on", first_tmux)
            self.assertIn("@continuum-restore 'on'", first_tmux)
            self.assertIn("-- personal", first_hypr)
            self.assertIn('hl.unbind("SUPER + W")', first_hypr)
            self.assertIn('o.bind("SUPER + Q", "Close window"', first_hypr)

    def test_dry_run_only_checks(self) -> None:
        backend = FakeBackend()
        paths = DotfilesPaths(Path("/repo"), Path("/state"), Path("/config"))
        run_dotfiles(
            paths=paths, backend=backend, assume_yes=False, dry_run=True,
            stdin=io.StringIO(), stdout=io.StringIO(), progress=False,
        )
        self.assertEqual(backend.calls, ["check"])
