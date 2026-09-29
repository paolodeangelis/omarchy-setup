# Disposable Omarchy system tests

These workflows are implemented but have not yet passed a real VM run. No
compatible runner was registered when checked. Unit tests do not certify them.

## Run on GitHub

Register a **dedicated disposable Arch/Omarchy runner**, not your workstation,
with labels `self-hosted, linux, x64, omarchy, kvm, disposable`. Provision Python
3.11+, Git, curl, OpenSSH, QEMU, edk2-ovmf, socat, ImageMagick, Tesseract and its
English data. Give the runner access to `/dev/kvm`. The pinned official harness
expects firmware under `/usr/share/edk2/x64/`. Allow ample disk space for an ISO,
installed guest and application packages. The host adapter installs no packages.
Guest internet access is required for repositories, AUR and weather data.

Set repository Actions variable `OMARCHY_VM_RUNNER_ENABLED=true` only after
registering that runner. Do not enable these privileged jobs for untrusted PRs.

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
account login, multi-monitor behavior, Spaces hover/settings and frame-by-frame
animation remain separate acceptance work. A VM failure may expose an existing
utility compatibility defect; do not weaken tests merely to obtain green CI.

Never run `guest.sh` or package-removal acceptance on your workstation. The
runtime guard is defense in depth, not permission to use a persistent machine.
