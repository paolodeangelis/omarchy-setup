# Deblob module instructions

- Removal targets must come from explicit repository configuration.
- Treat every unknown package as retained.
- Plan Pacman's complete transaction before requesting sudo.
- Abort when a transaction touches a protected package.
- `--yes` may skip confirmation only; it must not skip safety checks.
- Apply package removal through `omarchy pkg drop`.
- Verify targets are absent and protected packages remain installed.
- Tests must use fake package state and must never mutate the host package database.
