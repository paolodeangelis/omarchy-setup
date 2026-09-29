# Disposable Omarchy VM tests

- Run these tests only inside a disposable VM created by the official Omarchy ISO harness.
- Never run package-removal acceptance tests on the host or a persistent workstation.
- Do not store real credentials, SSH keys, or tokens in fixtures.
- Package installation may run only in the disposable guest, never on the host.
- The official harness may provide its disposable guest password through the environment. Use an ephemeral askpass helper, never write the password itself, and revoke sudo afterward.
- Never pass `--login` in CI; account onboarding is interactive and must remain on the user's machine.
- Read `.github/AGENTS.md` for pinned/latest/upgrade coverage requirements. Test the installed utility in the guest, not just its Python mocks.
- Live doctor/GUI acceptance requires a ready desktop session and checks of resulting state; successful IPC or missing diagnostics must not be reported as visual success.
