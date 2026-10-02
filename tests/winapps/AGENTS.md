# WinApps CI smoke instructions

- These tests run only on an ephemeral GitHub-hosted runner with direct KVM access.
- Never run the Windows guest smoke on the workstation or inside the nested Omarchy VM.
- Generate credentials at runtime, keep them out of command output and artifacts, and destroy the guest disk at job teardown.
- A passing smoke proves only pinned WinApps/Windows-container RDP integration and launch of the built-in Notepad and Edge applications.
- It does not prove Office licensing, Dropbox collaboration, presentation displays, graphics quality, or Omarchy desktop rendering.
- Preserve logs and screenshots, but never upload the guest disk, FreeRDP certificates, askpass helper, or credentials.
