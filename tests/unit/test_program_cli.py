from __future__ import annotations

import unittest
import io
from contextlib import redirect_stdout

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


if __name__ == "__main__":
    unittest.main()
