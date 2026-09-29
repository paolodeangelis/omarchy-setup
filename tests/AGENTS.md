# Test instructions

- Derive assertions from accepted behavior and supported interfaces, not only the current implementation. A fixture must not silently add custom APIs to a stock-compatibility test.
- For bug fixes, add a focused regression that fails before and passes after where practical. If reproduction requires a GUI/VM, record that limitation and the separate acceptance procedure.
- Mock external effects for Python unit/orchestration tests. Keep all writes in temporary roots; never install/remove host packages, use real credentials, or restart the real desktop from these tests.
- Cover setup no-op/idempotency, failure preservation, unsupported inputs, and privilege boundaries when affected. Keep `-y` subject to the same safety checks.
- Separate evidence levels: Python logic, orchestration, real QML loading, visual behavior, and disposable Omarchy VM compatibility. File-existence checks, fake builds, and successful IPC calls prove only their own layer.
- Desktop acceptance must exercise the reported interaction, allow rendering/content loading, and inspect relevant runtime errors. Immediate open/close is only an IPC smoke test; screenshots alone do not prove smooth animation.
- Missing logs, unavailable displays, or skipped VM runs must be reported as unavailable/skipped, never healthy/passed.
- Run affected tests during iteration and relevant broader suites before handoff. Do not repeatedly run unrelated expensive checks against unchanged code.
- See `tests/vm/AGENTS.md` for disposable-VM restrictions. Never substitute the user's workstation when a VM is unavailable.
