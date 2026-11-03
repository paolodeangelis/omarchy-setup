from __future__ import annotations

import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from omarchy_setup.cli import build_parser, main


class ProgramCliTests(unittest.TestCase):
    def test_all_accepts_automatic_login_and_default_flags(self) -> None:
        args = build_parser().parse_args(["install", "all", "-y", "-l", "-d"])

        self.assertEqual(args.command, "install")
        self.assertEqual(args.target, "all")
        self.assertTrue(args.yes)
        self.assertTrue(args.login)
        self.assertTrue(args.set_defaults)

    def test_install_only_is_available_for_noninteractive_preparation(self) -> None:
        args = build_parser().parse_args(
            ["install", "winapps", "-y", "--install-only"]
        )

        self.assertTrue(args.install_only)

    def test_spelling_compatibility_aliases_are_accepted(self) -> None:
        args = build_parser().parse_args(
            ["install", "zen", "--loggin", "--defoult"]
        )

        self.assertTrue(args.login)
        self.assertTrue(args.set_defaults)

    def test_install_ls_is_documented_and_lists_protocols(self) -> None:
        args = build_parser().parse_args(["install", "ls"])
        self.assertEqual(args.target, "ls")
        help_output = io.StringIO()
        with self.assertRaises(SystemExit) as exit_info:
            with redirect_stdout(help_output):
                build_parser().parse_args(["install", "-h"])
        self.assertEqual(exit_info.exception.code, 0)
        self.assertIn("ls", help_output.getvalue())

        output = io.StringIO()
        self.assertEqual(main(["install", "ls"], stdout=output), 0)
        listing = output.getvalue()
        self.assertIn("Available installation protocols:", listing)
        self.assertIn("mamba", listing)
        self.assertIn("winapps", listing)
        self.assertIn("run separately", listing)
        self.assertIn("Zen Browser", listing)
        self.assertIn("all", listing)

    def test_uninstall_requires_one_named_program(self) -> None:
        args = build_parser().parse_args(["uninstall", "zen", "-y"])

        self.assertEqual(args.command, "uninstall")
        self.assertEqual(args.target, "zen")
        self.assertTrue(args.yes)

    def test_upgrade_preserves_target_check_source_and_yes_contract(self) -> None:
        targeted = build_parser().parse_args(
            ["upgrade", "bluebubbles", "--check", "--source", "-y"]
        )
        interactive = build_parser().parse_args(["upgrade"])

        self.assertEqual(targeted.command, "upgrade")
        self.assertEqual(targeted.target, "bluebubbles")
        self.assertTrue(targeted.check_only)
        self.assertTrue(targeted.source)
        self.assertTrue(targeted.yes)
        self.assertIsNone(interactive.target)

    @patch("omarchy_setup.cli.run_upgrade", return_value=0)
    def test_upgrade_dispatch_preserves_global_yes(self, run_upgrade) -> None:
        output = io.StringIO()

        self.assertEqual(main(["-y", "upgrade", "all", "--check"], stdout=output), 0)

        self.assertEqual(run_upgrade.call_args.args[0], "all")
        self.assertTrue(run_upgrade.call_args.kwargs["assume_yes"])
        self.assertTrue(run_upgrade.call_args.kwargs["check_only"])

    def test_dotfiles_supports_automatic_and_dry_run_modes(self) -> None:
        args = build_parser().parse_args(["dotfiles", "-y", "--dry-run"])

        self.assertEqual(args.command, "dotfiles")
        self.assertTrue(args.yes)
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()
