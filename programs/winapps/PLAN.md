# WinApps manual-first installation plan

## Outcome and stop condition

Build one upstream WinApps-managed Windows VM that:

- launches Word, Excel, and PowerPoint as Linux desktop applications;
- opens, edits, saves, and reopens files from the Linux home and Dropbox folders;
- provides a full Windows desktop fallback;
- preserves the team's editable PowerPoint layout in a Mac → Windows → Mac round trip;
- distinguishes ordinary Dropbox file exchange from live Office co-authoring;
- lets PowerPoint use a physical second display for the slide show and the laptop display for Presenter View;
- can be removed at the integration layer without deleting the Windows guest or documents.

Establish the manual installation and file workflow before implementing the Python installer. The user currently has no external monitor: installation, single-screen Office use, and later automation of verified steps may proceed, with presentation support explicitly pending. Physical two-monitor acceptance is required before claiming Presenter View support; three-monitor support requires its own physical test.

For daily-use acceptance, also complete the team-deck round trip and a three-working-day pilot below. WinApps runs real Windows Office; it does not make Windows and Mac PowerPoint identical or add cloud collaboration to a redirected drive.

## Audit corrections and next action

The earlier plan described a plausible architecture, not a proven workstation setup.

- The earlier Docker-group/KVM observations came from a restricted tool environment (`nobody` groups, `/dev/kvm` absent, system bus denied). They do not establish host permissions or that Omarchy intentionally configured this account that way. Repeat those checks in the actual host session before choosing the backend.
- Rootless Podman is the current candidate, not a reliability result. Do not rotate backends repeatedly: perform one capability probe, record its result, and use the simplest supported working lifecycle. Do not change groups or privilege policy implicitly.
- Running a pinned `setup.sh` does not pin the installed source. At the reviewed revision, `waGetSourceCode` clones or pulls the default upstream branch, including before uninstall. Resolve this before installation: review the actual fetched revision and explicitly record drift, or use a narrowly reviewed, tested mechanism to prevent the fetch. A detached checkout alone can make `git pull` fail and is not a solution. Automation remains blocked until source acquisition is reproducible.
- The Compose template mounts `./oem:/oem`. Copy the complete reviewed `oem/` directory alongside the active Compose file (or use an explicit resolved mount). Verify it contains `install.bat`, registry files, and referenced PowerShell scripts before boot. Otherwise Windows can install without the expected RemoteApp configuration.
- `+home-drive` maps the user's home itself: `~/Dropbox/deck.pptx` becomes `\\tsclient\home\Dropbox\deck.pptx`, with no extra username component.

Next execution step: host preflight, then a short full-desktop Windows/Office pilot using a representative team deck. Establish file fidelity before investing in seamless windows or additional applications. The external-display test remains required before presentation acceptance.

## Reviewed upstream baseline

Reviewed on 2026-09-30:

- WinApps repository: `winapps-org/winapps`
- reviewed commit: `42c7e8318280c6fc3426c7afebfc7f43b895f4c8`
- official Docker/Podman guide: `docs/docker.md`
- official configuration and setup guide: `README.md`
- official installer/remover: `setup.sh`
- VM engine in the reviewed compose file: `ghcr.io/dockur/windows`

Primary references (recheck at installation time):

- [WinApps guide](https://github.com/winapps-org/winapps/blob/42c7e8318280c6fc3426c7afebfc7f43b895f4c8/README.md)
- [Docker/Podman guide](https://github.com/winapps-org/winapps/blob/42c7e8318280c6fc3426c7afebfc7f43b895f4c8/docs/docker.md)
- [Installer source](https://github.com/winapps-org/winapps/blob/42c7e8318280c6fc3426c7afebfc7f43b895f4c8/setup.sh)
- [Office cloud fonts](https://support.microsoft.com/en-us/office/fonts/cloud-fonts-in-office)
- [Font embedding](https://support.microsoft.com/en-us/office/fonts/benefits-of-embedding-custom-fonts)
- [Dropbox Office co-authoring](https://help.dropbox.com/view-edit/collaborate-on-microsoft-office)
- [PowerPoint collaboration through OneDrive/SharePoint](https://support.microsoft.com/en-us/powerpoint/work-together-on-powerpoint-presentations)

The manual installation must record the actual selected WinApps commit and container-image digest. Do not automate from a moving branch or mutable `latest` tag.

## Repository and runtime ownership

Tracked in this repository:

- `programs/winapps/PLAN.md`: procedure, checkpoints, evidence, and unresolved decisions;
- `programs/winapps/AGENTS.md`: subsystem safety and compatibility rules;
- future secret-free `compose.yaml` and `winapps.conf` templates, added only after manual validation;
- future Python orchestration in `src/omarchy_setup/modules/programs/`;
- future fake-backend tests and opt-in VM acceptance tests under `tests/`.

Runtime files remain outside Git:

- `~/.config/winapps/compose.yaml`: active Podman Compose definition;
- `~/.config/winapps/winapps.conf`: active RDP configuration, mode `0600`;
- `~/.local/bin/winapps-src/`: upstream source copied by a user installation;
- `~/.local/share/winapps/`: detected applications, icons, and runtime data;
- rootless Podman volume `winapps_data`: Windows system disk and installed Office;
- `~/.local/share/winapps/winapps.log`: debug log;
- FreeRDP certificates below `~/.config/freerdp/`.

Passwords, tokens, Windows product keys, Office credentials, and Dropbox credentials must never enter this repository, terminal history, logs, screenshots, or CI artifacts.

## Backend decision

Evaluate the upstream WinApps rootless Podman backend first. Confirm the actual host state before treating it as the selected backend. The paths and later steps below describe this candidate.

Reasons:

- Podman is an officially documented WinApps backend with the managed lifecycle;
- application discovery, start/pause behavior, and removal paths match upstream;
- it avoids maintaining two lifecycle controllers for the same VM;
- rootless Podman does not require root-equivalent Docker-group membership;
- upstream Omarchy shared-directory relaunch reports justify a version-specific check; they do not prove this host is affected.

Earlier command discovery saw Docker and did not find Podman, `podman-compose`, `crun`, or FreeRDP on the tool's PATH; host availability remains to be verified. Upstream WinApps invokes its runtime directly during normal launches. Rootful Docker socket access is root-equivalent, but Docker also has a rootless mode: do not claim all Docker use requires Docker-group membership. Check what is already supported/configured before installing another runtime.

Checkpoint 1 must prove rootless Podman and KVM access. If it cannot, stop and reconsider the Omarchy-managed VM with `WAFLAVOR=manual`; do not silently switch to an unsafe Docker configuration.

Preserve useful Omarchy security properties:

- bind VNC and RDP ports to `127.0.0.1` only;
- do not add the user to the `docker` group;
- use KVM through rootless Podman with `crun`, following upstream's `keep-groups` requirements when necessary;
- prefer `RDP_ASKPASS` over a plaintext `RDP_PASS`;
- use a user-scoped WinApps installation.

## Linux files and Dropbox

The accepted first configuration will use FreeRDP `+home-drive`, because this is the upstream WinApps path-mapping mechanism. During an RDP or RemoteApp session Windows sees the Linux home as `\\tsclient\home`, including the Dropbox directory.

The upstream compose template separately bind-mounts the entire home as `/shared`, exposed by the VM as `\\host.lan\Data`. That duplicates full-home access and remains available whenever the VM is running. During the manual setup, prefer one of these alternatives and record the result:

1. remove the `/shared` home mount and rely on `+home-drive`; or
2. narrow `/shared` to the Dropbox directory while retaining `+home-drive` for WinApps path translation.

Start with option 1 to keep one canonical document path. Add a separate share only for a demonstrated need. Never apply container ownership conversion such as `:U` recursively to Home or Dropbox. Verify host ownership/modes before and after any bind-share experiment.

Allowing `+home-drive` means Windows software can read and modify everything the Linux user can access under the home directory. Before testing, confirm Dropbox recovery/version history and use disposable document copies. Disable untrusted Office macros.

## Team collaboration and layout contract

User clarification: Dropbox Family; Office likely supplied by Duke (exact assigned entitlement unverified); simultaneous editing is not currently required. The primary acceptance path is sequential Dropbox exchange with Mac colleagues. Live co-authoring is optional and must not block this installation.

Dropbox Family is not among the plans listed for Dropbox's Microsoft Office desktop co-authoring integration. However, Dropbox's [Office integration FAQ](https://help.dropbox.com/integrations/microsoft-office-faq) explicitly includes Family for Office Online editing and supports simultaneous editing of documents in shared folders. The team prefers Dropbox: for occasional live work, first test everyone opening the same shared `.pptx` through Dropbox's PowerPoint for the web integration. This keeps the document in Dropbox and needs no WinApps. Validate the actual team deck in the web editor before adopting it.

Live editing in desktop PowerPoint through WinApps requires the separate eligible Dropbox team-plan/Office integration; opening a redirected file does not enable it. Do not mix ordinary desktop edits of the synced file with a live web editing session. OneDrive/SharePoint remains an optional alternative only if the user chooses it. Keep one authoritative document location.

Duke documents an assigned Microsoft 365 A5 license as a prerequisite for desktop installation: [Duke installation guidance](https://oit.duke.edu/help/articles/kb0028849/). Verify the user's available desktop-app entitlement and activation inside the VM during onboarding; do not infer a license solely from affiliation.

Two workflows need separate validation:

- File exchange: edit `\\tsclient\home\Dropbox\...` using Windows PowerPoint, close it, wait for Linux Dropbox to finish syncing, then hand it to the next editor. A local Office lock file is not a cross-machine Dropbox collaboration lock. Use an agreed single-editor handoff until real co-authoring is proven.
- Simultaneous editing: open the cloud document through a supported Office integration. Dropbox documents eligible team plans, a qualifying Microsoft 365 business license, and adding Dropbox for Teams as a storage location in Office. Opening a Linux redirected path is not evidence that this integration is active. Test AutoSave, collaborator presence, comments, edits from both platforms, and version history. If the team's entitlement does not support this, discuss its existing OneDrive/SharePoint workflow or use sequential Dropbox editing; do not silently migrate team storage.

Keep Linux Dropbox as the owner of its existing sync directory. Do not point a second Windows Dropbox client at the same redirected folder. Do not store the live VM disk inside Dropbox. If a Windows cloud client proves necessary, design its separate local storage and avoid duplicate competing edit paths.

Before choosing Office editions or declaring compatibility, record the team's Mac PowerPoint versions, template, required fonts, Dropbox/Office entitlement, and whether simultaneous editing is needed. Prefer real Microsoft PowerPoint in the guest and the team's current `.pptx` format. Avoid saving team decks through another presentation editor during this experiment.

Use Office cloud fonts available on both platforms, or install matching licensed font versions in Windows and macOS. Linux-installed fonts are not automatically installed in Windows. Where a font permits editable embedding, embed all characters for collaborators; a subset limits subsequent editing. Do not silently substitute a corporate font or change the template.

Test a copy of a real team deck with dense text, slide masters, charts, equations, scientific figures, SVG/EMF content, embedded/linked media, notes, comments, animations, and any required add-ins. Audit linked local files: Windows paths and Mac paths are not interchangeable. Embed portable assets where appropriate while preserving editability.

Mac acceptance procedure:

1. Obtain a representative `.pptx` and Mac-exported PDF reference from the user through the normal team workflow; keep confidential content and screenshots outside Git.
2. Open it in Windows PowerPoint without saving; compare text wrapping, clipping, symbols, master layout, figure position, chart labels, and media against the reference.
3. Make representative text/figure/comment edits, save a new `.pptx`, and export a PDF.
4. Have a colleague open that `.pptx` in Mac PowerPoint, inspect it, make an edit, and save it back; reopen it in Windows.
5. Require no unexpected layout changes, repair prompts, lost content, or lost editability. Differences in text antialiasing alone are not layout failures. Use exported PDFs for static comparisons and actual slideshow playback for media/animations. A PDF is a reference, not a substitute for the editable deliverable.

Without the actual Mac round trip, report layout fidelity as unverified. WinApps itself cannot guarantee it.

## Guided manual procedure

Verify each checkpoint before continuing. Continue ordinary authorized steps without repeated approval requests; pause for personal sign-in, needed user observations, or a material unresolved choice.

### Checkpoint 1: read-only preflight

Record:

- `omarchy version` and kernel version;
- CPU virtualization and `/dev/kvm` access;
- Docker state for conflict detection, plus Podman, `podman-compose`, and `crun` availability;
- available RAM and disk space;
- `freerdp` package and client versions;
- current monitor layout from `hyprctl monitors all`;
- whether `ip_tables` and `iptable_nat` are loaded;
- KVM ownership/mode and whether rootless Podman can open it;
- rootless runtime prerequisites (user namespaces, subordinate UID/GID mappings, and `crun` device access), plus coexistence with existing Docker workloads;
- absence or exact state of existing WinApps containers and volumes in both Docker and Podman, plus config, launchers, and FreeRDP certificates.

If an existing installation or guest disk is discovered, inspect ownership and health and prefer reuse where appropriate. Preserve unknown guest data; request a decision only if adopting or replacing it materially changes scope.

### Checkpoint 2: choose and record inputs

Proposed initial VM resources for this workstation:

- Windows 11 Pro;
- 8 GiB RAM;
- 4 CPU cores;
- 128 GiB virtual disk;
- local-only ports `127.0.0.1:8006` and `127.0.0.1:3389` TCP/UDP.

Choose a Windows username and password interactively. The password must not be written to a repository template. Use a password-manager-backed `RDP_ASKPASS` command if practical; otherwise keep a local mode-`0600` secret during the experiment and migrate it after validation.

### Checkpoint 3: prepare a pinned source and configuration

- Install the official Arch packages required for rootless Podman, `podman-compose`, `crun`, FreeRDP 3, and the remaining WinApps dependencies through supported Omarchy/package interfaces.
- Prove the container runtime is rootless and uses `crun` before creating the VM.
- Clone or download an explicit reviewed WinApps revision; do not run the official moving `main` URL through process substitution.
- Verify the commit and record it above.
- Copy and edit the upstream compose file under `~/.config/winapps/`.
- Preserve the matching `oem/` assets and resolve the source-fetch issue described above before invoking setup.
- Replace the mutable container tag with a reviewed tag or digest.
- retain localhost-only port mappings;
- apply the chosen `/shared` policy from the file-access section;
- set `WAFLAVOR="podman"`, `RDP_IP="127.0.0.1"`, and `RDP_PORT="3389"`;
- retain the upstream initial flags `/cert:tofu /sound /microphone +home-drive`;
- keep `DEBUG="true"` during validation;
- leave `/multimon` out of RemoteApp flags initially;
- reserve `/multimon` for `RDP_FLAGS_WINDOWS` after baseline full-desktop success.

Inspect the effective Compose model locally before starting it; redact passwords before capturing evidence. It must not publish ports to the LAN or mount unexpected host paths. Keep first-boot credentials in a local private file and verify the selected image's credential handling; `RDP_ASKPASS` only covers the later RDP connection. Inspect web-console authentication independently of localhost binding.

### Checkpoint 4: create Windows

- Start the reviewed Compose file with `podman-compose` in the foreground so progress and failures are visible.
- Open the local web console at `http://127.0.0.1:8006`.
- Complete Windows setup using a password-capable local account.
- Apply Windows updates and reboot until settled.
- confirm Windows is Pro, Enterprise, or Server and that RDP works;
- install and activate Office legitimately;
- install no additional Windows software until the baseline is captured.

Record the Windows build, Office build/channel, container image digest, and actual resource allocation.

### Checkpoint 5: prove the RDP baseline

Before running the WinApps setup wizard:

- connect using FreeRDP 3 with certificate trust-on-first-use;
- verify keyboard, mouse, clipboard, sound, microphone, scaling, suspend/reconnect, and graceful shutdown;
- verify `\\tsclient\home` and the selected Dropbox/share path;
- test a harmless file create, rename, modify, save, and delete cycle;
- inspect logs for authentication, certificate, drive-redirection, and graphics errors.

Do not continue if full desktop RDP is unstable.

### Checkpoint 6: install WinApps integration

- Run the reviewed `setup.sh --user` only after resolving its automatic source fetch; verify the resulting source revision. Do not use `--system`.
- select only Word, Excel, PowerPoint, and the full Windows desktop initially;
- verify `winapps`, `winapps-setup`, desktop files, icons, MIME handlers, and source/data paths;
- restart the application launcher if necessary and confirm the launchers appear;
- keep WinApps debug logging enabled until acceptance is complete.

### Checkpoint 7: Linux/Dropbox file acceptance

Use disposable `.docx`, `.xlsx`, and `.pptx` files with spaces, accented characters, and Unicode in their names.

For each type:

1. open it from the Linux file manager;
2. confirm the intended Windows Office application opens as a RemoteApp;
3. edit and save in place;
4. close the application completely;
5. verify Linux ownership, mode, size, modification time, and readable content;
6. reopen it from Linux;
7. perform Save As into Dropbox;
8. confirm Dropbox finishes syncing and version history contains the change.

Also test PDF export, clipboard text/image transfer, file locking, a disconnected RDP session, and graceful VM shutdown. Never use a valuable original for failure testing.

Complete the Mac round trip and the selected collaboration workflow from the team contract. Record sequential sharing and live co-authoring as distinct results.

### Checkpoint 8: physical multi-monitor PowerPoint acceptance

Deferred until an external display is available; this does not block installation or single-screen editing. Keep `RDP_FLAGS_WINDOWS=""` initially. Virtual displays can exercise software behavior but do not prove actual scaling, projector output, hotplug, or Presenter View on this machine.

Connect the actual external display or projector before starting the RDP session. Record the Hyprland layout, resolutions, scales, rotations, primary display, and FreeRDP monitor list. Use a non-overlapping layout.

First test a full Windows desktop using `RDP_FLAGS_WINDOWS="/multimon"`; do not use `/span`.

Acceptance requires:

- Windows sees two distinct displays in extended mode;
- PowerPoint shows the audience slide on the external display;
- Presenter View, notes, timer, and next-slide preview remain on the laptop;
- mouse and keyboard coordinates are correct on both screens;
- embedded audio/video, `F5`, `Shift+F5`, pointer controls, and display selection work;
- reconnect, monitor unplug/replug, and sleep/wake recover predictably.

Only after that passes, test RemoteApp PowerPoint with `/multimon` as an experiment. If it blacks out, flashes, misplaces windows, or misroutes input, preserve full-desktop multi-monitor as the supported presentation path.

Repeat separately for a third monitor before claiming three-monitor support.

### Checkpoint 9: restart and update resilience

- stop and start the container repeatedly;
- reboot Linux and verify the VM does not become unintentionally network-accessible;
- rerun `winapps-setup --user --add-apps` and confirm idempotent launcher behavior;
- perform one controlled Windows update and retest RDP, RemoteApp, files, and Presenter View;
- retain a recoverable guest backup before testing WinApps, FreeRDP, or container-image updates.

Run a three-working-day pilot with normal-sized team decks. Record cold/warm launch time, save time, memory use, crashes, recovery, and whether dialogs or authentication become inaccessible in RemoteApp. Verify a graceful stop and a restorable powered-off VM backup before risky updates. Keep AutoRecover enabled in Windows and test recovery on a disposable file. Avoid automatic pause during active editing/co-authoring until tested.

Retain a clearly labelled full-desktop launcher. Switching from RemoteApp to full desktop may disrupt the current Windows session; save first and test the transition rather than promising seamless coexistence. Additional Windows-only apps receive their own launch/file/add-in/peripheral tests; successful Office tests do not certify every Windows app.

## Removal model

Removal has three deliberately separate scopes.

### Integration removal: safe default

Plan to use reviewed upstream `winapps-setup --user --uninstall` after addressing its pre-uninstall source fetch. Inventory affected launchers and MIME defaults first: the reviewed remover scans launcher contents, so verify it will not remove unrelated user wrappers. Restore only associations owned by our installation. It removes WinApps launchers, scripts, desktop entries, icons, and generated application data. Upstream deliberately preserves:

- `~/.config/winapps/`;
- the WinApps source checkout;
- the Podman container and `winapps_data` Windows disk;
- Office and user documents.

The Python utility's default WinApps uninstall must match this preservation behavior and verify every removed/retained path.

### Runtime removal: preserve Windows disk

Stopping and removing the Podman container/Compose objects without deleting `winapps_data` is a separate operation. It must inventory the exact Compose project and volume before acting and verify that the Windows data volume remains.

### Guest purge: destructive and exceptional

Deleting `winapps_data` destroys Windows, Office, and guest-resident data. It must use a dedicated narrow option, show the exact volume and backup state, and require explicit destructive confirmation. Generic `-y` is insufficient. Never remove unrelated Docker images, containers, volumes, FreeRDP certificates, packages, or user files.

Dependencies such as Podman, `podman-compose`, `crun`, FreeRDP, Git, `dialog`, `iproute2`, `libnotify`, and `openbsd-netcat` are shared system components and are not automatically removed.

## Python implementation after manual acceptance

Implement WinApps as a dedicated program kind rather than forcing it into the current single-command package model.

Required lifecycle:

1. `inspect`: versions, capabilities, existing data, ports, mounts, secrets mechanism, and monitor evidence;
2. `plan`: exact packages, source revision, image digest, paths, mounts, and interactive steps;
3. `apply`: install prerequisites and source/config templates without storing secrets;
4. `onboard`: Windows/Office setup and application selection in a visible interactive session;
5. `verify`: RDP, launchers, file round trips, container scope, and recorded manual multi-monitor evidence;
6. `remove-integration`: preserve guest/config/source by default;
7. optional `purge-guest`: explicit destructive operation with independent safety gates.

`omarchy-setup install all -y` must not claim WinApps success while Windows or Office onboarding remains incomplete. It may prepare verified prerequisites and report `onboarding required`, or skip WinApps with that explicit state. CI can test planning, templates, state transitions, fake backends, and uninstall preservation, but cannot certify Office licensing or physical multi-monitor behavior.

## Evidence record

Fill this only while executing the guided installation:

- [x] preflight captured
- [x] pinned WinApps revision and container digest recorded
- [x] effective Compose mounts/ports reviewed
- [ ] Windows and Office installed and versions recorded
- [x] baseline full desktop RDP passed
- [x] WinApps user integration installed
- [x] Word file round trip passed
- [x] Excel file round trip passed
- [x] PowerPoint and Dropbox file round trip passed
- [ ] real team deck Mac → Windows → Mac fidelity passed
- [ ] sequential sharing / live co-authoring result and entitlements recorded
- [ ] full-desktop two-monitor Presenter View passed
- [ ] RemoteApp multi-monitor result recorded
- [ ] optional three-monitor test passed
- [x] restart/update resilience passed
- [ ] three-working-day pilot and backup/restore passed
- [ ] integration-only uninstall preservation proved
- [ ] Python implementation authorized
