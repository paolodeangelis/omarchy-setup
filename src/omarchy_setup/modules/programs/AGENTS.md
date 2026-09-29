# Programs module instructions

- Prefer supported `omarchy` installers and package helpers over direct package-manager calls.
- Keep the registry explicit. Unknown programs must fail without installing anything.
- Separate detection, installation, default selection, login launch, and verification.
- Login hooks may launch an application or browser, but must never collect or store credentials.
- `-y` suppresses only this project's confirmation; compatibility and verification remain mandatory.
- Mamba uses a pinned, checksum-verified Miniforge installer under the user's XDG data directory; keep base inactive and append only a marked block to the user's shell rc.
- Do not run `conda init` or edit Omarchy-owned files under `/usr/share/omarchy`; preserve the existing Omarchy/mise/Starship startup order.
- Tests must use fake backends and temporary paths. Never install software on the developer machine.
