# omarchy-setup agent instructions

## Project purpose

`omarchy-setup` is a personal, reproducible configuration framework for an Omarchy Linux installation.

The repository is the source of truth for the desired machine configuration.

The user normally experiments manually first. Once a setup works and is understood, encode the minimal reproducible procedure in this repository.

Do not redesign working user configuration without a reason.

## Core principles

- Prefer simple, understandable solutions over abstractions.
- Keep configuration files in their native format and directly editable.
- Prefer supported Omarchy interfaces when available.
- Do not modify Omarchy-owned files under `/usr/share/omarchy`.
- Unknown packages/programs default to KEEP.
- Never remove software merely because it is not listed in this repository.
- Operations must be idempotent where practical.
- Re-running a successful operation should normally produce no changes.
- Never store passwords, tokens, private keys, account credentials, or other secrets in the repository.
- Runtime logs, backups, caches, and generated state belong outside the repository.

## Repository locations

Canonical repository:

`~/.omarchy-setup`

Runtime state:

`~/.local/state/omarchy-setup`

User-accessible launcher:

`~/.local/bin/omarchy-setup`

Keep generated/runtime state out of Git.

## Architecture

Use Python as the main orchestration layer.

Use Bash only when shell commands are the natural implementation.

The root `omarchy-setup` launcher may contain the minimal shell bootstrap necessary before the Python environment exists.

Micromamba manages the dedicated Python environment used by `omarchy-setup`.

Do not depend on whichever Conda/Mamba environment happens to be active in the user's shell.

Prefer standard-library Python unless an external dependency provides clear value.

## CLI

Planned top-level interface:

`omarchy-setup init`

`omarchy-setup doctor`

`omarchy-setup deblob`

`omarchy-setup programs <name>`

`omarchy-setup programs all`

`omarchy-setup programs list`

`omarchy-setup programs status`

`omarchy-setup dotfiles`

`omarchy-setup theme`

`omarchy-setup verify`

`omarchy-setup all`

Global behavior:

- `-y` / `--yes` suppresses ordinary confirmation prompts.
- `-y` must never bypass compatibility, validation, or safety failures.
- `--install-only` installs programs but skips personal configuration, authentication, and interactive onboarding.
- Do not introduce a generic `--force` flag. Use narrowly scoped override flags when genuinely necessary.

## Modules

Prefer the lifecycle:

`inspect -> plan -> apply -> verify`

Keep inspection and planning separate from mutation when practical.

Dry-run functionality should use the same inspection/planning logic as real execution.

Do not report success based only on a command exit code when resulting state can also be verified.

## Programs

Programs live behind:

`omarchy-setup programs <name>`

Installation priority:

1. Supported Omarchy installation mechanism.
2. Omarchy package helpers.
3. Official Arch package.
4. AUR or upstream-supported installation.
5. Custom installation.

Do not bypass an existing supported Omarchy installer just to simplify implementation.

A program may implement:

`detect -> install -> configure -> onboard/authenticate -> verify`

Not every program needs every phase.

Account credentials must never be automated by storing secrets in this repository.

`--install-only` skips configuration and account onboarding that require personal or GUI interaction.

For complicated programs such as WinApps, first establish and understand a working manual setup. Then encode only the reproducible parts.

## Dotfiles

Store real editable configuration under `dotfiles/`.

Do not generate large native configuration files from opaque Python structures unless there is a compelling technical reason.

Prefer:

`dotfiles/hypr/...`

over Python code that constructs Hyprland configuration text.

Before replacing an existing user configuration, preserve it when appropriate.

Do not overwrite unrelated user changes silently.

## Themes and assets

Themes belong under `themes/`.

Wallpapers, icons, images, and similar repository-managed resources belong under `assets/`.

Keep source assets separate from runtime/generated files.

## Deblob

Deblob operations are explicitly configured.

Never infer that an unknown application should be removed.

Before removing a package, consider whether Omarchy or another retained component depends on it.

Prefer Omarchy-supported removal mechanisms where available.

Destructive operations require meaningful verification.

## Safety

This project modifies the user's operating system.

Before destructive or difficult-to-reverse changes, inspect relevant state and explain unexpected risk.

Do not:

- pipe passwords into `sudo`
- store sudo credentials
- run the entire application as root
- delete unknown user data
- modify `/usr/share/omarchy`
- silently bypass failed safety checks

Acquire sudo privileges only for operations that require them.

`sudo -v` may be used to establish a sudo session when appropriate.

Prefer configuration rollback/backups for files. Do not claim package operations are transactionally reversible when they are not.

## Omarchy compatibility

Do not assume an Omarchy internal path or command is stable across releases.

Use documented/supported interfaces when possible.

Version-specific behavior should be isolated rather than scattered throughout unrelated modules.

Unsupported versions should fail safely rather than guessing.

## Tests

Every meaningful behavior should be testable without modifying the real machine where practical.

Use:

- unit tests for Python logic
- integration tests for orchestration/state behavior
- full Omarchy VM tests for actual system compatibility

Tests involving disposable fixtures or temporary directories may run without asking for approval.

Changes that affect destructive operations, package handling, bootstrap, compatibility, or privilege use require relevant tests.

Test idempotency for setup operations:

`apply -> verify -> apply -> verify`

The second application should normally require no changes.

## Git and changes

Keep commits focused.

Do not commit secrets, machine-generated state, logs, caches, or credentials.

Before committing, inspect the diff.

Do not rewrite unrelated user changes.

Do not create commits unless the user asks for a commit or the current task explicitly includes committing.

## Communication

Be concise.

For ordinary implementation work, report:

- what changed
- relevant files
- tests/results
- unresolved issues

Avoid long explanations of obvious code.

For destructive operations, security-sensitive changes, architectural decisions, or ambiguous system behavior, use normal clear prose rather than aggressive compression.
