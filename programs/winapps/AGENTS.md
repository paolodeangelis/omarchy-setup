# WinApps subsystem instructions

- Inherit the repository root instructions and the programs module instructions.
- Establish a working manual installation before encoding it in Python.
- Treat rootless Podman as a candidate pending actual host preflight. Sandbox groups, device visibility, and socket permissions do not prove host configuration. Do not change privilege policy implicitly.
- Pin every reviewed upstream revision or image digest before automation; never execute an unreviewed `main` installer through `curl | bash`.
- Keep Windows, Office, WinApps, Docker, and RDP credentials out of Git. Repository templates must contain placeholders only.
- Treat the Windows guest disk and user documents as user data. Removing WinApps integration must preserve them by default.
- A VM purge is a distinct destructive operation and must require explicit scope, an inventory, and a backup warning. `-y` must not turn an integration removal into a VM purge.
- Do not add the user to the `docker` group merely to avoid privilege prompts; membership is root-equivalent.
- Prove local-file round trips and physical multi-monitor PowerPoint behavior before claiming support. A single-monitor VM or mocked test is not sufficient evidence.
- Record exact WinApps, FreeRDP, container-image, Windows, Office, Omarchy, and monitor-layout versions for the accepted setup.
- Preserve the user's Home/Dropbox access requirement. Test sequential syncing separately from Office cloud co-authoring; never run two sync clients against the same local directory.
- Require a real team-deck Mac → Windows → Mac round trip and matching fonts before claiming layout compatibility. Store private decks and evidence outside Git.
- Check upstream installer self-updates and matching OEM assets. A pinned entry script alone does not establish reproducible installation or removal.
