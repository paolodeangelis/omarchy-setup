# TODO

## Bootstrap
- [x] Implement root `omarchy-setup` launcher
- [x] Implement `omarchy-setup init`
- [x] Install/verify pinned `uv`
- [x] Create dedicated `omarchy-setup` environment
- [x] Install project CLI
- [x] Create `~/.local/bin/omarchy-setup`
- [x] Install repository-managed Bash completion for commands, programs, plugins, and theme modes

## Core
- [x] Implement `doctor` (shell/IPC, OSD/menu, keybindings, helper commands, recent errors, optional UI smoke)
- [ ] Implement command runner
- [ ] Implement global `-y`
- [ ] Implement dry-run architecture
- [ ] Implement state/log directories
- [x] Add shared progress reporting to init, install, deblob, and theme workflows
- [x] Add evidence-first, scope-preserving agent guidance and layered tests/pinned-latest VM requirements

## Programs
- [x] Define initial program registry
- [x] Implement `install all` and independent installation
- [x] Add explicit login and Omarchy-default hooks
- [ ] Implement `programs list`
- [ ] Implement `programs status`
- [x] Implement `--install-only`
- [x] Add explicit single-program uninstall with preserved user data and safe exclusions for Miniforge/WinApps
- [x] Add source-aware upgrade checks, an interactive selector, independent Flatpak updates, and supported full-system Omarchy updates
- [x] Add disposable-VM acceptance for upgrade source reporting; unit tests prove source-specific delegation without mutating the VM package state
- [x] Add Zen, 1Password, Dropbox, Spotify, WhatsApp, and Telegram
- [x] Add ClickUp through its maintained AUR package backed by the official Linux AppImage
- [x] Add Proton VPN CLI and selectable OmaProton/general VPN bar integrations
- [x] Avoid Proton GUI's duplicate-launch Python/native crash with a managed single-instance desktop launcher; two repeated launcher activations reused the live process without a new core dump
- [x] Add LibreOffice with US English/Italian spelling and US English hyphenation
- [x] Add Zotero with interactive account and sync onboarding
- [x] Add BlueBubbles through existing system Flatpak/Flathub with install, onboarding, detection, and preservation-safe removal
- [x] Add Thunderbird as the default mail client; retain disabled Omamail install/remove support
- [ ] Evaluate the managed ONLYOFFICE Desktop Editors install with real DOCX/PPTX round trips before considering its heavier self-hosted server stacks; ONLYOFFICE 10 currently leaves its XWayland editor invisible after exiting presentation mode (upstream Hyprland #16436 / ONLYOFFICE #2530), so presentation use remains unverified
- [ ] Validate Zen's managed Window Sync opt-out and persistent independent `Super+Shift+B` windows across a reboot
- [x] Add an Outlook web-app protocol with interactive login and notification onboarding
- [x] Install native Zoom through `install all`, make it the meeting-link handler, and retain `zoom-web` as an optional fallback
- [ ] Confirm native Zoom package, launcher preservation, protocol defaults, and idempotency in successful pinned/latest/upgrade VM runs
- [ ] Validate Proton VPN sign-in, connection, kill switch, and suspend/resume in disposable/current Omarchy environments; both bar integrations are disabled because Proton 4.18.7 forbids CLI access while its desktop app is running
- [x] Add Miniforge-backed `mamba` with an Omarchy-safe shell integration
- [x] Review upstream WinApps and record a manual-first install, acceptance, and preservation-safe removal plan in `programs/winapps/PLAN.md`
- [x] Audit WinApps plan for Mac layout fidelity, Dropbox co-authoring, sandbox/host evidence, OEM assets, and installer source drift
- [x] Replace the moving WinApps installer path with a pinned source/image preparation lifecycle and verify actual host prerequisites
- [ ] Validate a real team-deck Mac/Windows round trip, sharing workflow, and three-working-day pilot
- [ ] Finish guided WinApps evidence: exact Windows/Office versions, real team deck, physical multi-monitor, and backup/restore pilot
- [ ] Finish WinApps lifecycle beyond pinned preparation: guided credentials/onboarding, status, application rescan, and verification reporting
- [ ] Implement integration-only WinApps uninstall that preserves the guest disk and user data by default
- [x] Add explicit WinApps preparation plus direct-KVM Notepad/Edge smoke gated after each configured Omarchy release-upgrade run; verified by workflow run `37084133207`

## Configuration
- [x] Deploy a verified Fontconfig alias for Mac PowerPoint's `CMU Serif Roman` full-face reference while retaining directly editable native configuration
- [x] Deploy idempotent shell aliases alongside managed tmux and Hyprland settings
- [x] Manage tmux layout persistence and the Super+Q close-window override
- [x] Theme management
- [x] Implement fixed-liquid and floating bar appearances (currently both use the overlay)
- [x] Reach user-accepted bar appearance and popup spacing; preserve this visual baseline
- [x] Move Olio bar geometry into a live-reloaded TOML file
- [x] Validate Olio native theme TOML before activation
- [x] Add fixed-mode shell overrides, restart the live shell when their effective theme changes, and provide literal floating popup-gap control
- [x] Resolve shell surface colours from the native theme palette during installation
- [x] Preserve the Olio overlay environment for bar-launched Omarchy commands
- [x] Keep Spaces after Menu (replacing stock Workspaces), Weather Radar after Weather, and Notification Center rightmost in both bar modes
- [x] Move managed plugins out of theme activation into `omarchy-setup plugin`; keep IDs, sources, placement, and safe replacements editable in `plugins/plugins.toml`
- [x] Manage the built-in `omarchy.media` widget after Spaces without cloning Omarchy-owned source
- [x] Preserve Omarchy 4.5's built-in Elsewhen world clock beside the clock in managed bar layouts
- [x] Preserve Elsewhen cities across shell restart/resume with Omarchy's reviewed blocking startup-load fix (upstream #13221); local cold-restart verification retained Rome and the remaining configured cities
- [x] Keep the clock screen-centered while Omarchy 4.5 reveals inactive indicators on bar hover
- [x] Keep application defaults and shortcuts editable in `config/apps.toml`
- [x] Screen-clamp oversized floating popups so Notification Center keeps the right-side gap
- [x] Restore Notification Center own-service access through host-owned widget construction; visually verify fresh messages in both modes
- [x] Align notification toast offsets with the accepted bar popups in both modes; preserve notification borders
- [x] Audit Omacale 0.39.0 popup lifecycle and document a fixed-only compatibility-safe animation plan (source analysis, not measured video proof)
- [x] Add fixed-only retained popup geometry and spatial morphing; locally verify rapid reversal, floating gap, Notification Center, Spaces preview, menu, and OSD
- [x] Track theme wallpapers with descriptive filenames and validated same-stem artwork metadata
- [x] Add a bottom-layer artwork-info control, working background-picker shortcut, and 24-hour wallpaper rotation to the Olio shell
- [ ] Framework-specific configuration

### Deferred compatibility follow-up

These audit findings are not authorization to change the accepted desktop. Reproduce against current state when a relevant task is requested; visual acceptance does not establish stock or upgrade compatibility.

- [ ] Restore/prove floating stock-shell compatibility, including optional `PluginBarApi.barMargins` absence and fixed-mode fallback
  - Local Omarchy 4.5.0-3 check passed for `theme bar-stock`: Olio theme/background and configured plugin layout were retained, stock Weather and notification surfaces rendered below the stock bar, and floating mode restored cleanly. Disposable-VM fallback coverage remains.
- [ ] Reconcile Omarchy 4.5 bar drift without retuning Olio: preserve six-section placement semantics, glassy mode, display-cutout/per-output sizing, and current drag behavior; add a stock-layout migration check so new built-in widgets cannot be silently omitted
- [ ] Preserve the stock Display shortcut when Hyprmoncfg replaces `omarchy.monitor`; the live replacement currently has no `omarchy.monitor` IPC target
- [ ] Validate the local widget-host extension in pinned/latest/upgrade VMs (unit/JavaScript, offscreen QML, and local desktop checks pass; upstream support remains pending)
- [ ] Investigate Notification Center's DND control separately: its cross-service lookup is outside the own-service permission scope
- [ ] Investigate why the stock 10% low-battery warning was delivered only after a later shell restart at 8%; treat notification generation/queueing separately from the notification-center plugin
- [ ] Verify floating renderer parity and TOML gap/height semantics without retuning accepted geometry
- [x] Confirm in the 4.0.6 -> 4.5 VM that the new native popup/morph adapter, six-section layout folding, and complete stock-shell restore all work (run `42305684630`)
- [x] Repair the 4.5 popup geometry contract locally: floating cards include the island edge margin, fixed liquid surfaces no longer cover bar icons, and legacy plugin preview bars no longer emit an undefined-size warning
- [x] Teach Omarchy 4.5's notification deck to honor Olio's placement with stock fallback, and provide `theme bar-stock` while retaining the Olio theme
- [x] Stop module double-clicks from leaking into the bar-background gesture and make Olio activation clear a previously persisted transparent state
- [x] Wait for the previous Quickshell instance to exit before launching a rebuilt overlay; locally verified after the 4.0.5 workstation update
- [ ] Make doctor detect QML property-assignment errors and distinguish missing evidence from healthy checks
- [ ] Add real QML/VM acceptance for both styles, third-party previews, service-backed content, keyboard menus, and OSD
- [ ] Complete pointer-driven radar preview/Spaces hover, translucent, Tab/repeated-click, multi-output, fallback, and restore animation acceptance
- [ ] Pin or record reviewed companion-plugin revisions so fresh installs do not silently consume newer upstream code
- [x] Keep Battery Insights after the tray without replacing stock `omarchy.power`; repository/manifest and live loading are verified
- [x] Restore stock `omarchy.tray` after the TyRichards tray proved incompatible with Omarchy 4's plugin sandbox; retain its source disabled for rollback and keep plugin widgets on the visible bar
  - Olio consumes module double-clicks before the bar-background gesture and reconciles Spotlight/Dictation to `Alt+Space` / `Super+Alt+D`.
- [x] Reject the archived Shavanced notification-center replacement on Qt 6.12 (`Color.*` resolves undefined), restore the qualified-color Jankees center, and keep the failed source disabled for rollback evidence
- [x] Manage Hyprmoncfg after Audio; install/verify its daemon before replacing stock Monitor
- [ ] Physically validate Hyprmoncfg profiles across external-display hotplug, suspend/resume, lid changes, and rollback
- [ ] Visually verify Weather Radar after Weather with retained Omastorm disabled
- [ ] Add Weather Radar install, preview interaction, service/network behavior, and restore/fallback checks to pinned/latest/upgrade VM acceptance
- [ ] Add Spaces acceptance in pinned/latest/upgrade VMs: workspace switching, hover preview, settings panel, inline persistence, stock restoration, and multi-output IPC-handler behavior
- [ ] Validate Claude Spaces attention hooks; Codex 0.160.0 hook execution, active-shell routing, PID association, and visible waiting badge are verified
- [ ] Resolve WinApps/FreeRDP 13x13 stale RemoteApp clients automatically; rootless Podman makes upstream `winapps killrdp` track the wrapper PID, while the project now installs a safe manual `winapps-clean-ghost` workaround that acts only on tracked marker-only sessions
- [ ] Reconfirm in the pinned VM that Olio plugin-facade teardown errors are gone; exact 4.0.4 stock panel null-style warnings are classified separately and all other runtime errors still fail

## Deblob
- [ ] Inventory clean Omarchy installation
- [ ] Classify removable/default applications
- [x] Implement explicit package-list planning
- [x] Implement explicit package-list application
- [x] Implement package-state verification
- [ ] Add optional feature groups and matching service/config cleanup
- [x] Remove configured Omarchy web apps separately from Pacman packages and replace stale default handlers
- [ ] Validate removal policy in Omarchy VMs

## Testing / CI
- [x] Unit-test framework
- [x] Integration tests
- [x] GitHub Actions basic CI
- [x] Add non-mutating pre-commit checks and matching CI gate, including Actions lint and fast fixture tests
- [x] Cover release skip/checksum failure, guarded harness adaptation and missing/error-filled shell logs with unit tests
- [x] Consolidate commit-triggered pinned, fresh-candidate, configured-upgrade, and WinApps checks behind one version-named workflow plus a monthly/manual release detector
- [x] Pin the workstation target to Omarchy 4.5.0 while retaining the reviewed 4.0.6 seed ISO until an official 4.5.0 ISO exists
- [ ] Establish Omarchy 4.0.6 disposable VM execution through focused acceptance on the GitHub-hosted KVM runner
- [ ] Complete focused VM acceptance: theme modes/companions, deterministic panels/menu/OSD, restore, idempotency and actual deblob; remove dependency on unrelated Omarchy product/live-weather tests
  - Run `39159884581` passed setup, hooks, doctor, and shell-log checks on all targets, then exposed a stale visual check for disabled `omarchy.monitor`; the harness now exercises its active `crmne.hyprmoncfg` replacement.
  - Runs `42228153858`–`42250468160` exposed separate failures hidden by aggregate OCR reporting: transient undefined Loader components and onboarding windows opened by `install all`. Acceptance now normalizes Loader inputs, uses an empty visual workspace, and records compositor clients/layers plus exact terminal failures. Confirmation is pending.
  - Run `42255121009` stopped before visual acceptance because the harness used Hyprland's removed legacy workspace dispatcher; it now uses Omarchy's Lua `hl.dsp.focus` interface. Confirmation is pending.
  - Run `42264503002` passed the pinned VM and every upgrade operation before final visuals; workspace 9 renamed the active dynamic workspace instead of isolating it. Visuals now use configured empty workspace 5, and nested blank result names are removed. Confirmation is pending.
  - Run `42268950230` attempt 2 proved the final menu was rendered behind the 1Password onboarding client left open by `install all`. Run `42291755963` rejected the obsolete `closewindow` dispatcher; visual cleanup now uses `hl.dsp.window.close`. Run `42295315540` passed that cleanup and all configured style visuals, then exposed a stock-menu IPC startup race after restore; the actual summon now retries only known startup failures. Confirmation is pending.
- [ ] Confirm fresh Omarchy 4.0.6 VM acceptance with the reviewed shell-interface hashes
- [ ] Run configured 4.0.6 -> candidate-release upgrade-path VM test; fresh installation alone cannot certify workstation updates
- [ ] Restore full program-install coverage on a historical baseline only if an immutable 4.0.6 package snapshot becomes available; live Arch repositories upgrade it to 4.5.0, so CI plans programs before the upgrade and applies them afterward
  - Run `39157319202` accepted the reviewed interfaces; its 4.0.4 phases showed generic shell readiness precedes the Spaces IPC handler, so acceptance now waits for that specific handler. Confirmation is pending.
  - Run `39161736581` passed both fresh targets, then proved the active 4.0.4 overlay was stale after the 4.0.5 update. Theme activation now installs an official post-update hook that rebuilds the selected bar style; VM confirmation is pending.
