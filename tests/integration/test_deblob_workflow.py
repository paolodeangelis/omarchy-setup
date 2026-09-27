from __future__ import annotations

import io
import unittest

from omarchy_setup.modules.deblob import DeblobConfig, DeblobError, run_deblob


class NoReadInput(io.StringIO):
    def readline(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("confirmation prompt was read despite --yes")


class FakeBackend:
    def __init__(
        self,
        installed: set[str],
        transaction: tuple[str, ...],
        *,
        browser: str | None = "brave-browser.desktop",
    ) -> None:
        self.installed = set(installed)
        self.transaction = tuple(sorted(transaction))
        self.browser = browser
        self.privilege_requests = 0
        self.removals = 0

    def check_environment(self) -> str:
        return "4.0.4-1"

    def installed_packages(self) -> set[str]:
        return set(self.installed)

    def plan_removal(self, packages: tuple[str, ...]) -> tuple[str, ...]:
        return self.transaction

    def default_browser(self) -> str | None:
        return self.browser

    def acquire_privileges(self) -> None:
        self.privilege_requests += 1

    def remove(self, packages: tuple[str, ...], *, quiet: bool) -> None:
        self.removals += 1
        self.installed.difference_update(self.transaction)


def run(
    config: DeblobConfig,
    backend: FakeBackend,
    *,
    assume_yes: bool = True,
    dry_run: bool = False,
) -> tuple[int, str]:
    output = io.StringIO()
    result = run_deblob(
        config,
        backend=backend,
        assume_yes=assume_yes,
        dry_run=dry_run,
        quiet=False,
        progress=False,
        stdin=NoReadInput(),
        stdout=output,
    )
    return result, output.getvalue()


class DeblobWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DeblobConfig(
            remove=("chromium", "notes-app"),
            protected=frozenset({"base", "omarchy"}),
        )

    def test_yes_applies_and_verifies_without_prompt(self) -> None:
        backend = FakeBackend(
            {"base", "omarchy", "chromium", "notes-app", "unused-library"},
            ("chromium", "notes-app", "unused-library"),
        )

        result, output = run(self.config, backend)

        self.assertEqual(result, 0)
        self.assertEqual(backend.privilege_requests, 1)
        self.assertEqual(backend.removals, 1)
        self.assertEqual(backend.installed, {"base", "omarchy"})
        self.assertIn("Unused dependencies (1):", output)
        self.assertIn("unused-library", output)

    def test_second_run_is_idempotent_and_needs_no_sudo(self) -> None:
        backend = FakeBackend({"base", "omarchy"}, ())

        result, output = run(self.config, backend)

        self.assertEqual(result, 0)
        self.assertEqual(backend.privilege_requests, 0)
        self.assertEqual(backend.removals, 0)
        self.assertIn("Nothing to remove", output)

    def test_dry_run_uses_plan_without_mutating(self) -> None:
        backend = FakeBackend(
            {"base", "omarchy", "chromium", "notes-app"},
            ("chromium", "notes-app"),
        )

        result, output = run(self.config, backend, dry_run=True)

        self.assertEqual(result, 0)
        self.assertEqual(backend.privilege_requests, 0)
        self.assertEqual(backend.removals, 0)
        self.assertIn("Dry run complete", output)

    def test_protected_transaction_is_rejected_before_sudo(self) -> None:
        backend = FakeBackend(
            {"base", "omarchy", "chromium", "notes-app"},
            ("base", "chromium", "notes-app"),
        )

        with self.assertRaisesRegex(DeblobError, "protected packages: base"):
            run(self.config, backend)

        self.assertEqual(backend.privilege_requests, 0)
        self.assertEqual(backend.removals, 0)

    def test_chromium_removal_requires_replacement_default_browser(self) -> None:
        backend = FakeBackend(
            {"base", "omarchy", "chromium", "notes-app"},
            ("chromium", "notes-app"),
            browser="chromium.desktop",
        )

        with self.assertRaisesRegex(DeblobError, "still the default browser"):
            run(self.config, backend)

        self.assertEqual(backend.privilege_requests, 0)


if __name__ == "__main__":
    unittest.main()
