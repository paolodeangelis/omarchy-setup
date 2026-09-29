# Theme module instructions

- Never edit `/usr/share/omarchy`. An existing user-owned overlay is a compatibility mechanism, not a requirement to route every theme operation through a shell fork.
- Read `themes/olio-su-silicio/AGENTS.md` for the shared visual/compatibility contract before changing theme orchestration.
- Inspect and plan before activation. Validate candidates in staging and preserve the last working state when validation fails.
- Check all upstream interfaces touched by the overlay, not just a `KeyboardPanel.qml` marker. Detect upstream changes affecting reused overlays; unsupported inputs must fail safely, including with `-y`.
- Do not infer stock compatibility from a successful overlay run. Optional native modules and extended plugin APIs need separate absence/fallback coverage.
- Build native QML modules from vendored source; do not commit machine-built binaries.
- Companion widgets must be installed through `omarchy plugin`. Enable and place a replacement before disabling its built-in counterpart; preserve the command needed to restore the built-in widget.
- Verify activation and restore against the resulting launcher, environment, plugin selection, and shell state. Restoring only the UWSM override is not proof of a complete stock restore; preserve unrelated user changes.
- Tests must use temporary roots and must not restart the real desktop.
