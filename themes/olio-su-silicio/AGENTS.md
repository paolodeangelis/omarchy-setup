# Olio su Silicio theme instructions

- `omarchy-theme/` is the native Omarchy theme and wallpaper source.
- Preserve the user-accepted appearance and geometry. Do not retune spacing, transparency, or animation while fixing unrelated integration behavior.
- Target contract: floating mode uses ordinary rounded, detached popups with the stock Omarchy shell; fixed mode adds optional liquid attachment. Do not blur these two behaviors.
- Current exception: both modes use the custom overlay, and stock fallback/update compatibility is not fully verified. Preserve the working setup; resolve this debt only in a scoped compatibility task (see root `TODO.md`). Do not claim the target contract is already met.
- Keep user-tunable bar geometry in `plugins/olio.bar/bar.toml`; malformed values must fall back safely.
- `shell/KeyboardPanel.qml` and `bin/omarchy-launch-shell` support the custom overlay. Treat every touched upstream interface, including `PluginBarApi` and service access, as version-sensitive compatibility code.
- Optional properties such as `barMargins` must not break stock plugin API initialization when absent. Check errors and object initialization before adjusting popup coordinates.
- Keep third-party plugin source unchanged during bar integration work; use supported host interfaces and preserve scoped service access.
- The managed workspace replacement is `tornikegomareli.spaces`, placed after `omarchy.menu`; install/enable it before disabling `omarchy.workspaces`. Its hover preview, settings panel, and inline settings persistence are acceptance checks in both bar modes. Restore the stock widget if Spaces cannot be enabled.
- `shell/OlioHostedWidgets.js` and `shell/OlioHostedBarWidget.qml` are a version-pinned host extension, installed by `modules/theme/host_integration.py`. Only the host creates configured registry widgets with their own service facade; never replace this with a generic service getter on the bar. QML object-tree sharing is not a security sandbox.
- Reproduce the actual interaction: clicking Omastorm's bar widget opens its preview; summoning its standalone panel does not test that preview.
- For shared bar/panel changes, check both styles with a built-in popup, a third-party popup, and a service-backed popup. Check backgrounds, corners, gaps, edge placement, switching/closing, and content loading. Include keyboard menus and OSD when shared shell behavior is affected.
- Inspect screenshots for static appearance and recordings or live transitions for animation claims. Command success or a popup opening is insufficient. Record unavailable visual checks rather than claiming completion.
- Prove stock fallback separately from overlay rendering in a disposable environment. Live desktop testing must be within the user's requested scope; restore temporary test state afterward.
- Do not commit compiled QML modules, runtime overlays, logs, or backup files here; those belong under `~/.local/state/omarchy-setup`.
