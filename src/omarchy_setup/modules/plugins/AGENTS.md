# Plugin module instructions

- Manage third-party shell plugins only through supported `omarchy plugin` and
  `omarchy bar` interfaces; never patch plugin source.
- Keep desired IDs, sources, placement, and explicit replacements in
  `plugins/plugins.toml`, not Python constants.
- Install, validate, enable, and position a replacement before disabling its
  predecessor. Retain third-party predecessor source for rollback.
- Upgrades apply only to registry-managed plugins and must use Omarchy's
  validation/rollback-aware updater.
- Unit tests must cover idempotent reconciliation, replacement ordering,
  invalid manifests/configuration, and upgrade target selection.
