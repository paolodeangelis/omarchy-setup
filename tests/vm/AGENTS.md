# Disposable Omarchy VM tests

- Run these tests only inside a disposable VM created by the official Omarchy ISO harness.
- Never run package-removal acceptance tests on the host or a persistent workstation.
- Do not store real credentials, SSH keys, or tokens in fixtures.
- Keep the first VM slice non-destructive: verify bootstrap, idempotency, and deblob planning.
