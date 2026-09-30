# Disposable Omarchy system tests

These workflows use an ephemeral GitHub-hosted Ubuntu runner with KVM. They are
implemented but remain unverified until a complete real VM run passes. Unit
tests do not certify them.

## Run on GitHub

The shared workflow provisions QEMU, OVMF, ImageMagick and Tesseract on
`ubuntu-24.04`, verifies `/dev/kvm`, and gives the guest 5 GiB. It adapts only
reviewed host-path differences in the pinned official harness. The VM workflow
is manual/release-triggered and never runs for pull requests. Guest internet
access is required for repositories, AUR and weather data.

In Actions, manually run:

- **Pinned Omarchy**: fresh baseline, utility bootstrap, apps, both themes,
  repeatability, restore, deblob, doctor and upstream desktop checks.
- **Upgrade Omarchy**: same configured baseline disk, official updater, reboot,
  tests before any repair/reapply, then setup checks.
- **Latest Omarchy**: fresh latest stable release with the same acceptance.

See workflow display names in `.github/workflows/omarchy-*.yml`. Latest and
upgrade explicitly skip when no newer official release exists. Version and ISO
checksum resolution failures fail the job; they never substitute an older ISO.
Edit `releases.json` when deliberately advancing your workstation baseline.
Review its checksum and the pinned official ISO harness commit together.

The release watcher polls every six hours on the default branch and dispatches
the two candidate workflows. GitHub schedules can be delayed. Its cache prevents
routine duplicates, but cache eviction or a partial dispatch can cause a repeat;
it is not an exactly-once release webhook. Failed runs can be rerun manually.

## Evidence and limits

Actions handles triggers, permissions, runners and artifacts. Small Python
helpers resolve exact releases/checksums and adapt the pinned upstream harness;
Bash runs setup inside the installed guest. The adapter syncs **tests only**, not
upstream product code. Upgrade restarts the same disk rather than reinstalling.

Artifacts include manifests, package lists, shell logs, screenshots, OCR and
failures. Guest disks, SSH keys and firmware state are excluded. Screenshots and
mapped layers are not proof of smooth animation: inspect them manually. Hardware,
account login, multi-monitor behavior, radar preview clicks, Spaces hover/settings and frame-by-frame
animation remain separate acceptance work. A VM failure may expose an existing
utility compatibility defect; do not weaken tests merely to obtain green CI.

`coverage.json` explicitly records UI checks still missing. Radar's standalone
panel must never stand in for its bar-widget preview. Missing shell logs or QML
assignment/load errors fail runtime acceptance rather than count as healthy.

Never run `guest.sh` or package-removal acceptance on your workstation. The
runtime guard is defense in depth, not permission to use a persistent machine.
