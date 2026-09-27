# omarchy-setup

Personal, reproducible setup and configuration framework for Omarchy.

The goal is to reproduce my preferred Omarchy installation while keeping the configuration understandable, editable, testable, and safe to update.

## Scope

The project will manage:

- bootstrap and required setup tools
- removal of unwanted default applications
- program installation and configuration
- interactive account onboarding when required
- dotfiles
- themes, wallpapers, icons, and other assets
- machine-specific configuration
- development and scientific environments
- verification and compatibility tests
- CI testing against pinned and current Omarchy releases

## Core principles

- Prefer supported Omarchy interfaces when available.
- Keep native configuration files human-readable and directly editable.
- Unknown software is kept by default.
- Operations should be idempotent and safe to re-run.
- Destructive changes must be explicit and verified.
- `-y` suppresses ordinary prompts but never bypasses safety checks.
- `--install-only` installs software without interactive account/configuration setup.
- Secrets and credentials must never be committed.
- Runtime state, logs, caches, and backups do not belong in the repository.

## Planned CLI

```text
omarchy-setup init

omarchy-setup doctor

omarchy-setup deblob

omarchy-setup programs <name>
omarchy-setup programs all
omarchy-setup programs list
omarchy-setup programs status

omarchy-setup dotfiles
omarchy-setup theme
omarchy-setup verify

omarchy-setup all
```

The exact interface may evolve as the project is implemented.

## Deblob

The first implemented slice removes only packages explicitly listed in
`config/deblob.toml`. It inspects installed state, plans Pacman's complete
dependency transaction, rejects protected-package removal, asks for
confirmation and sudo, applies through `omarchy pkg drop`, then verifies the
result.

Preview the plan without changing the machine:

```bash
./omarchy-setup deblob --dry-run
```

Run without the ordinary confirmation prompt:

```bash
./omarchy-setup deblob -y
```

`-y` does not bypass compatibility, browser, dependency, or protected-package
safety checks.
