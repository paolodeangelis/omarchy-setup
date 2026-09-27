# Init module instructions

- Bootstrap from system Python, then run all commands from the dedicated `uv` environment.
- Keep the environment, uv binary, cache, metadata, and rollback environment under runtime state.
- Verify downloaded binaries against pinned SHA-256 values before extraction.
- Never overwrite an unrelated `~/.local/bin/omarchy-setup` entry.
- Build replacement environments at stable versioned paths, verify them, then switch the active symlink atomically.
- Keep one previous environment for manual rollback.
- Test with temporary paths and fake downloads; never change the developer's real environment.
