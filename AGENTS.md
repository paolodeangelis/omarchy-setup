# omarchy-setup agent instructions

## Project purpose

`omarchy-setup` is a personal, reproducible configuration framework for an Omarchy Linux installation.

The repository is the source of truth for the desired machine configuration.

The user normally experiments manually first. Once a setup works and is understood, encode the minimal reproducible procedure in this repository.

Do not redesign working user configuration without a reason.

## Task scope and convergence

- For substantial work, state the requested outcome, behavior to preserve, and evidence that will establish completion. Keep this brief; do not require a separate planning document for routine changes.
- Treat user-accepted behavior and configuration as the baseline. A new request changes only the relevant requirement; it does not discard earlier constraints.
- Distinguish investigation from implementation. Backlog items and audit findings are not authorization to repair unrelated behavior.
- Before fixing an uncertain failure, reproduce the exact command or interaction and inspect relevant state/logs. Separate observations from hypotheses; identify the responsible layer before editing.
- Make the smallest coherent change supported by the evidence. Do not combine a bug fix with visual redesign, refactoring, dependency replacement, or a broader compatibility workaround.
- If a fix fails, record what the result disproves and remove only your unsuccessful changes when safe. Do not stack speculative patches. After two failed attempts at the same symptom, pause edits and reassess the mechanism and test method; continue read-only diagnosis without asking permission again.
- Ask for clarification only when an unresolved choice materially affects behavior, safety, or scope. Continue authorized implementation and disposable tests without repeatedly asking the user to approve ordinary steps.
- Stop when the requested acceptance conditions are met. Report unrelated findings separately instead of extending the task.

## Efficient context and handoff

- Read applicable instructions and task-relevant code/tests, not the whole repository by default. Reuse established evidence unless the underlying state changed.
- Keep durable decisions and unresolved work in the relevant instructions and `TODO.md`; do not copy conversation transcripts or long debugging logs into them.
- Keep instructions consistent with each other. Distinguish desired contracts from known implementation exceptions so future agents neither assume compatibility nor silently redesign the working setup.
- When handing off unfinished work, record the exact remaining failure, evidence location, failed hypotheses, and next discriminating check. Do not restart an already completed investigation.

## Canonical project location

The canonical repository location is:

`~/.omarchy-setup`

Preserve this project location.

Do not move, duplicate, or recreate the repository elsewhere unless explicitly requested.

Scripts must determine the repository root robustly rather than hardcoding a username or absolute `/home/<user>` path.

Runtime state belongs under:

`~/.local/state/omarchy-setup`

The user-accessible launcher belongs under:

`~/.local/bin/omarchy-setup`

Keep generated/runtime state out of Git.

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

## AGENTS.md hierarchy

The root `AGENTS.md` contains project-wide rules.

Create additional `AGENTS.md` files at meaningful module or subtask boundaries when local instructions would improve development.

Examples:

`programs/winapps/AGENTS.md`

`programs/dropbox/AGENTS.md`

`src/omarchy_setup/modules/deblob/AGENTS.md`

`tests/AGENTS.md`

Do not create an `AGENTS.md` in every directory automatically.

Create one when a directory represents a distinct subsystem, workflow, safety boundary, or implementation area with instructions that differ from or extend the root rules.

Nested `AGENTS.md` files should:

- contain only instructions specific to that subtree
- inherit the root project rules
- avoid duplicating large portions of the root `AGENTS.md`
- remain concise
- document important assumptions, interfaces, safety constraints, and test requirements for that subsystem

Before modifying a subsystem, read the applicable root and nearest nested `AGENTS.md` instructions.

When creating a substantial new subsystem, consider whether it should receive its own `AGENTS.md`.

## Progress tracking

The root repository must contain:

`TODO.md`

`TODO.md` is the persistent project roadmap and progress tracker.

Before starting substantial work:

1. Read `TODO.md`.
2. Identify the relevant current task.
3. Avoid implementing later tasks accidentally unless required by the current task.

After completing meaningful work:

1. Update `TODO.md`.
2. Mark completed items.
3. Add newly discovered work where appropriate.
4. Record important blockers or unresolved decisions.
5. Keep the roadmap consistent with the actual repository state.

Do not mark work complete merely because code was written. Relevant verification/tests must pass first.

Keep `TODO.md` concise and useful. It is a project tracker, not a development log.

For complicated standalone subsystems, a local `TODO.md` may be created when useful, but the root `TODO.md` remains the authoritative high-level project tracker.

## Architecture

Use Python as the main orchestration layer.

Use Bash only when shell commands are the natural implementation.

The root `omarchy-setup` launcher may contain the minimal shell bootstrap necessary before the Python environment exists.

`uv` manages the dedicated Python environment used by `omarchy-setup`.

Do not depend on whichever Python environment happens to be active in the user's shell.

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

Optional extensions must be capability-checked before use and must not prevent baseline initialization. Do not label a customization failure an upstream limitation until it is reproduced against the installed stock interface.

Do not modify third-party plugins or bypass their permission/service boundaries to accommodate this repository's customization without an explicitly scoped task.

When evaluating an external implementation, inspect its installation, update,
rollback, compatibility checks, tests, and license—not only its appearance.
Treat release posts and screenshots as claims until the referenced code or a
published artifact contains the behavior. Record version/commit mismatches.

For managed third-party replacements, establish and verify the replacement
before disabling the built-in component. Keep an explicit restoration path,
and do not claim future-release compatibility without pinned/latest/upgrade VM
evidence.

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

Preserve requirement-based tests; do not weaken assertions merely to match a new implementation. Read `tests/AGENTS.md` before changing tests.

Match verification to the claim: mocked orchestration tests do not prove desktop rendering, stock compatibility, or upgrade safety. Report untested conditions explicitly; missing evidence is not a passing check.

Use focused checks during iteration and relevant broader checks before handoff. Documentation-only edits need content/diff checks, not desktop restarts or package operations.

The compatibility target is disposable GitHub Actions VM coverage for both the pinned workstation baseline (currently Omarchy 4.0.4) and the latest stable Omarchy release. Ubuntu unit tests are not a substitute. Read `.github/AGENTS.md` when changing workflows or claiming system compatibility.

When adding system-facing behavior, add its relevant VM acceptance coverage or explicitly record the missing coverage and leave compatibility unverified. A workflow file existing is not evidence of a successful run. Fresh-install compatibility and upgrading an already customized installation are separate claims.

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
