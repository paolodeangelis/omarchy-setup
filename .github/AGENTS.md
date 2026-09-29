# Workflow compatibility contract

- Maintain separate fresh-install targets for the pinned workstation baseline (currently Omarchy 4.0.4) and latest stable Omarchy. Never replace the pinned regression target with latest.
- Latest-release testing must have an explicit repeatable release-discovery/trigger mechanism, record the resolved version and verified ISO identity, and report resolution failures instead of silently retesting an older release.
- Run actual Omarchy compatibility checks inside disposable booted VMs with the required desktop/session services. Ubuntu CI or a container alone does not establish desktop compatibility.
- Read `tests/vm/AGENTS.md` before changing the VM harness. Runner prerequisites and missing runners must be explicit; never claim an unexecuted job passed.
- Acceptance must exercise the installed utility: bootstrap, relevant program/setup operations, idempotency, live doctor checks, both bar modes and third-party integration when affected. Include resulting-state assertions and applicable upstream acceptance checks, not only mocked unit tests.
- For upgrade-safety claims, also test the pinned configured VM upgraded to the candidate release without wiping its configuration. Passing a fresh candidate installation is insufficient.
- Preserve diagnostics on failure: exact versions/commits, failing commands, test results, relevant shell logs, and screenshots/recordings for visual checks. Avoid credentials and private user data in artifacts.
- Report coverage by target and layer. Missing GUI checks or a missing runner mean incomplete evidence; never convert them into a green compatibility result.
- Passing VM checks reduces risk, not all possible failures: document hardware/account-specific gaps and retain a targeted workstation smoke check and recovery plan for updates.
- These are required targets, not a description of completed CI. Consult root `TODO.md` for outstanding implementation; do not expand a documentation-only task into workflow implementation.
