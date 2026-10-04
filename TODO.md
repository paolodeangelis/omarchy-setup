# TODO

## Bootstrap
- [x] Implement root `omarchy-setup` launcher
- [x] Implement `omarchy-setup init`
- [x] Install/verify pinned `uv`
- [x] Create dedicated `omarchy-setup` environment
- [x] Install project CLI
- [x] Create `~/.local/bin/omarchy-setup`

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
- [x] Add Zen, 1Password, Dropbox, Spotify, WhatsApp, and Telegram
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
- [ ] Dotfile deployment
- [x] Theme management
- [x] Implement fixed-liquid and floating bar appearances (currently both use the overlay)
- [x] Reach user-accepted bar appearance and popup spacing; preserve this visual baseline
- [x] Move Olio bar geometry into a live-reloaded TOML file
- [x] Validate Olio native theme TOML before activation
- [x] Add fixed-mode shell overrides, restart the live shell when their effective theme changes, and provide literal floating popup-gap control
- [x] Resolve shell surface colours from the native theme palette during installation
- [x] Preserve the Olio overlay environment for bar-launched Omarchy commands
- [x] Keep Spaces after Menu (replacing stock Workspaces), Omastorm radar after Weather, and Notification Center after Power in both bar modes
- [x] Screen-clamp oversized floating popups so Notification Center keeps the right-side gap
- [x] Restore Notification Center own-service access through host-owned widget construction; visually verify fresh messages in both modes
- [x] Align notification toast offsets with the accepted bar popups in both modes; preserve notification borders
- [x] Audit Omacale 0.39.0 popup lifecycle and document a fixed-only compatibility-safe animation plan (source analysis, not measured video proof)
- [x] Add fixed-only retained popup geometry and spatial morphing; locally verify rapid reversal, floating gap, Notification Center, Spaces preview, menu, and OSD
- [ ] Assets management
- [ ] Framework-specific configuration

### Deferred compatibility follow-up

These audit findings are not authorization to change the accepted desktop. Reproduce against current state when a relevant task is requested; visual acceptance does not establish stock or upgrade compatibility.

- [ ] Restore/prove floating stock-shell compatibility, including optional `PluginBarApi.barMargins` absence and fixed-mode fallback
- [ ] Validate the local widget-host extension in pinned/latest/upgrade VMs (unit/JavaScript, offscreen QML, and local desktop checks pass; upstream support remains pending)
- [ ] Investigate Notification Center's DND control separately: its cross-service lookup is outside the own-service permission scope
- [ ] Verify floating renderer parity and TOML gap/height semantics without retuning accepted geometry
- [ ] Validate overlay reuse against all relevant upstream changes and verify complete stock restore
- [ ] Make doctor detect QML property-assignment errors and distinguish missing evidence from healthy checks
- [ ] Add real QML/VM acceptance for both styles, third-party previews, service-backed content, keyboard menus, and OSD
- [ ] Complete pointer-driven radar preview/Spaces hover, translucent, Tab/repeated-click, multi-output, fallback, and restore animation acceptance
- [ ] Pin or record reviewed companion-plugin revisions so fresh installs do not silently consume newer upstream code
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
- [ ] Validate removal policy in Omarchy VMs

## Testing / CI
- [x] Unit-test framework
- [x] Integration tests
- [x] GitHub Actions basic CI
- [x] Add non-mutating pre-commit checks and matching CI gate, including Actions lint and fast fixture tests
- [x] Cover release skip/checksum failure, guarded harness adaptation and missing/error-filled shell logs with unit tests
- [x] Consolidate commit-triggered 4.0.4, fresh-candidate, configured-upgrade, and WinApps checks behind one version-named workflow plus a six-hour release detector
- [ ] Validate the reviewed Omarchy 4.0.3 -> 4.0.4 drill (fresh 4.0.3, fresh 4.0.4, and configured upgrade) in GitHub Actions
  - Next run uses a guarded CI updater copy: same sudo TTY, restored upstream log, bounded status refresh, reboot deferred to the harness. Parallel targets and evidence-based per-step report implemented; end-to-end confirmation pending.
  - Run `37209688924` reached Omarchy 4.0.4 and passed doctor, panel/menu/notification OCR, and OSD checks; it falsely failed because the desktop journal query excluded current-boot startup messages. Run `37214026981` confirmed that fix; run `37217741459` showed cropped OCR works on the first two theme passes, but reads “probe” as “prove” after three retained notification cards accumulate. The matcher now checks the stable title prefix; a new VM rerun is required.
  - Audit follow-up: replace partial-upgrade package preparation with a reviewed baseline/repository policy; track all copied upstream shell inputs for overlay reuse; exercise actual WinApps preparation/launchers on Omarchy; add individual desktop/Windows assertions to the report and cache reviewed build inputs.
  - Run `37202409453` confirms the sudo fix passes pruning/snapshot creation; upgrade then rejected the theme overlay as a non-Git dev checkout. Added installed-root routing for update/version with executable fixture coverage; full VM upgrade/reboot verification remains pending.
- [ ] Re-run the reviewed drill after bounded retries for transient `omarchy-shell is not responding` plugin IPC startup failures
- [x] Establish Omarchy 4.0.4 disposable VM execution through focused acceptance on the GitHub-hosted KVM runner
- [ ] Complete focused VM acceptance: theme modes/companions, deterministic panels/menu/OSD, restore, idempotency and actual deblob; remove dependency on unrelated Omarchy product/live-weather tests
- [ ] Run fresh latest-stable Omarchy VM workflow when newer than baseline; currently latest equals 4.0.4
- [ ] Run configured 4.0.4 -> candidate-release upgrade-path VM test; fresh installation alone cannot certify workstation updates
