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

omarchy-setup install <name>
omarchy-setup install all
omarchy-setup programs list
omarchy-setup programs status

omarchy-setup dotfiles
omarchy-setup theme
omarchy-setup verify

omarchy-setup all
```

The exact interface may evolve as the project is implemented.

`omarchy-setup doctor` is read-only. It checks the running Quickshell instance,
menu/OSD IPC, critical system-menu/media bindings, helper commands, and recent
shell errors. Add `--ui` to summon and close every top-level Omarchy menu route
and issue a short OSD smoke call.

After switching a theme, an already-open terminal can retain the old
`OMARCHY_PATH`; that is reported as a note. Hyprland keybindings use the live
compositor environment, which the theme command updates.

## First run

Run initialization from the canonical checkout:

```bash
cd ~/.omarchy-setup
./omarchy-setup init
```

Initialization downloads a pinned, checksum-verified `uv`, creates a dedicated
Python environment under `~/.local/state/omarchy-setup`, installs this project,
and links `~/.local/bin/omarchy-setup` to the repository launcher. It does not
write generated environment files into the repository and does not need sudo.

Later commands use the environment automatically:

```bash
omarchy-setup deblob --dry-run
```

Re-running `omarchy-setup init` is safe. A changed project is built beside the
active environment and verified before activation. One previous environment is
kept under the state directory for manual rollback.

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

## Programs

Install every registered optional program without the project confirmation:

```bash
omarchy-setup install all -y

# list available installers and their descriptions
omarchy-setup install ls
```

Install one program and optionally open its login/onboarding flow or apply an
available Omarchy default:

```bash
omarchy-setup install zen --login --default
omarchy-setup install dropbox --login
```

Initial targets are Miniforge-backed `mamba`, `zen`, `1password`, `dropbox`,
`spotify`, `whatsapp`, and `telegram`. `mamba` installs a pinned,
checksum-verified Miniforge release under
`~/.local/share/omarchy-setup/miniforge3`, appends one marked integration block
to `~/.bashrc`, and leaves the base environment inactive. It does not run
`conda init` or edit Omarchy-owned files. Open a new terminal after installing,
then use normal commands such as:

```bash
omarchy-setup install mamba -y
mamba create -n science python numpy pandas
mamba activate science
mamba deactivate
```

The active named environment is shown by Starship's conda module when enabled
by the Omarchy prompt. `install all -y` includes mamba and skips every target
already detected as installed. Login is always interactive and credentials
remain with the application. At present only Zen has an applicable Omarchy
default.

## Theme

Install and activate the repository-owned `olio-su-silicio` theme with its
default fixed, full-width bar and Caelestia-style liquid popups:

```bash
omarchy-setup theme -y
omarchy-setup theme bar-fixed -y
```

Use the floating island with the shared Omarchy popup host; liquid rendering is
disabled in this mode so third-party widgets retain the stock popup contract:

```bash
omarchy-setup theme bar-floating -y
omarchy-setup theme status
```

Edit the floating geometry directly in
`themes/olio-su-silicio/plugins/olio.bar/bar.toml`. The bar watches this file,
so valid changes to its height, screen-edge margin, side margin, and popup gap
apply without rebuilding the liquid shell overlay. `floating.popup_gap` is the
literal distance between the painted island and its popup in logical pixels.

The base colour palette lives in
`themes/olio-su-silicio/omarchy-theme/colors.toml`. Shell surface entries use
quoted `palette.<key>` references; theme installation resolves them to native
hex values in managed runtime state. Shell opacity and structural settings
shared by both modes live in `shell.toml`. Fixed/liquid-only differences live
in the partial `shell-fixed.toml`; `theme bar-fixed` merges that file over the
common shell theme. The checked-in source files remain directly editable and
generated mode output stays out of Git.

Fixed liquid mode uses separate Wayland surfaces for the persistent bar and
the popup. Matching translucent alpha values match their RGBA configuration,
but the visible result can differ because each surface blends with different
content behind it. Use alpha `1.0` for an exactly constant joined colour.

Theme activation also verifies the companion Omarchy plugins. Spaces replaces
the built-in workspace switcher after Menu, Omastorm radar is placed after
Weather in the center group, and Notification Center is placed after Power at
the far right. Missing plugins are installed through Omarchy's plugin command;
re-running the theme command keeps their placement idempotent. Spaces is
enabled before `omarchy.workspaces` is disabled, so an installation failure
leaves the stock switcher available. Restore it manually with:

```bash
omarchy plugin enable omarchy.workspaces --section left --after omarchy.menu
omarchy plugin disable tornikegomareli.spaces
```

Notification Center archives notifications; it does not replace Omarchy's
floating notification toasts. Both bar styles use a version-checked host adapter
in the user-owned overlay: registered third-party widgets receive their own
scoped service access, while the replacement bar's service lookup remains
restricted. Toasts follow the existing bar-popup offset and retain Omarchy's
notification borders. No companion plugin source is patched.

The adapter checks the installed host/API/notification source fingerprints
before applying or reusing the overlay. Unknown versions are rejected; they
must be reviewed and tested before updating the accepted fingerprints. This is
a local compatibility extension, not an upstream API or proof of future-release
compatibility. Local tests include offscreen Qt widget loading when Qt and
Omarchy are available; fresh-install and upgrade VM coverage remains pending.

### Omacale comparison and update risk

[Omacale](https://github.com/AyushKr2003/omacale) replaces the complete bar
with a self-contained Caelestia-style shell: it owns its drawers, workspaces,
toasts, keyboard navigation, and third-party widget host. Its published code
draws the bar frame and drawers together as one screen-sized SDF blob, rather
than trying to reshape independent stock `KeyboardPanel` windows. Olio instead
keeps Omarchy's bar-widget ecosystem and changes the shared popup host only
where the fixed liquid attachment needs it. Omacale therefore achieves a more
coherent shell surface, but it has a much larger replacement surface.

Omacale reduces that risk with pre-install snapshots, exact uninstall restore,
an upstream-contract checker, and optional notification/lock clones rebuilt
from the installed Omarchy. Their watchdog can return a failed handover to the
stock implementation. Those are useful lifecycle patterns; they do not make a
full shell replacement automatically compatible with future Omarchy releases.

The earlier audit found a mismatch between the Reddit 0.37 announcement and
then-published 0.35.12 code. The 2026-09-29 audit inspected `a213d722` (0.39.0):
edge-dependent geometry is now source-verifiable. Its built-in popup morphing
and third-party compatibility paths are different, however. See the
[fixed-popup comparison and staged plan](docs/fixed-popup-animation-plan.md).
No new animation code was applied. Olio remains
version-gated and must pass pinned, latest, and configured-upgrade VM tests
before an Omarchy update is considered safe. Companion plugins are currently
installed from their upstream default branches on first setup, so a fresh
installation can also receive newer plugin code than this workstation;
pinning/reviewing those revisions remains open.

Theme assets, wallpapers, the custom bar, and Hyprland's rounded-window
override remain editable in this repository. The command links them into
`~/.config` and preserves replaced user files under
`~/.local/state/omarchy-setup/themes/olio-su-silicio/backups`. The liquid
overlay is built under the state directory and never modifies
`/usr/share/omarchy`. If the overlay is unavailable or incompatible, activation
rolls back safely. Restore only the stock shell explicitly with:

```bash
omarchy-setup theme restore -y
```

Interactive `init`, `install`, `deblob`, and `theme` runs show a tqdm progress
bar with the active step. Redirected output and CI use stable `[step/total]`
messages; `--quiet` suppresses normal install/bootstrap output.

## CI

### Fast checks before committing

From the repository root, use uv's isolated tool environment:

```bash
uv tool run --from pre-commit==4.2.0 pre-commit install
uv tool run --from pre-commit==4.2.0 pre-commit run --all-files
```

If `uv` is not on PATH, use `~/.local/state/omarchy-setup/bin/uv` after `init`.
Hooks check Python/YAML/TOML/JSON syntax, merge markers, private-key patterns,
large non-asset files, Actions definitions, Bash syntax and fast fixture tests.
They do not format files, run setup, request sudo or boot VMs. First use downloads
isolated tools (including actionlint's Go toolchain); subsequent runs reuse them.
QML runtime/rendering and visual animation require separate desktop acceptance.
The same hooks run in GitHub-hosted CI. Hook installation is opt-in per clone.

### System checks

Normal GitHub-hosted CI runs unit and fake-state integration tests on Ubuntu.
Three manual VM workflows cover fresh pinned Omarchy, configured baseline
upgraded to latest, and fresh latest. A release watcher dispatches candidate
tests when a newer official release appears. They use the pinned official ISO
harness and verified ISO checksums. A dedicated disposable KVM runner is
required; these workflows have not yet established a passing compatibility run.
See [runner setup, execution and coverage limits](tests/vm/README.md).
