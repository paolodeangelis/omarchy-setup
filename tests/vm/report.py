"""Render evidence-backed Actions results without copying aggregate statuses."""
import collections
import json
import os
from pathlib import Path
import sys


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")


def render(root, environment):
    lines = ["# Omarchy compatibility results", "",
             f"Baseline: **{cell(environment.get('BASELINE', 'unresolved'))}** · "
             f"Candidate: **{cell(environment.get('CANDIDATE', 'unresolved'))}**", "",
             "Job results below are aggregates. Individual recorded checks follow separately.", "",
             "| Job | Result |", "|---|---|"]
    for title, key in (("Fast checks", "CHECKS"), ("Release resolution", "RELEASE"),
                       ("Pre-commit and Action syntax", "PRE_COMMIT"),
                       ("Python compilation", "COMPILE"),
                       ("Unit and integration tests", "UNIT_INTEGRATION"),
                       ("Bootstrap CLI parsing", "BOOTSTRAP_CLI"),
                       ("Installer CLI parsing", "INSTALLER_CLI"),
                       ("Fresh baseline", "VERSION_BASELINE"), ("Fresh candidate", "FRESH_CANDIDATE"),
                       ("Configured upgrade", "UPGRADE_CANDIDATE"),
                       ("Windows RemoteApps on Ubuntu/Xvfb", "WINAPPS")):
        lines.append(f"| {title} | {cell(environment.get(key) or 'UNKNOWN').upper()} |")
    records = []
    problems = []
    for path in sorted(root.rglob("results-*.jsonl")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            try:
                row = json.loads(line)
                for key in ("target", "phase", "name", "status", "seconds", "exit_code"):
                    row[key]
                records.append(row)
            except (ValueError, KeyError, TypeError):
                problems.append(f"Unreadable result: {path.name}:{number}")
    counts = collections.Counter(row["status"] for row in records)
    lines += ["", "## Recorded acceptance checks", "",
              f"Passed: **{counts['PASS']}** · Failed: **{counts['FAIL']}** · "
              f"Total recorded: **{len(records)}**", "",
              "Unreached checks are not counted as passes or failures. Missing evidence remains UNKNOWN."]
    failures = [row for row in records if row["status"] != "PASS"]
    if failures:
        lines += ["", "### Failures", ""]
        for row in failures:
            lines.append(f"- **{cell(row['target'])}/{cell(row['phase'])}: {cell(row['name'])}** "
                         f"— exit {cell(row['exit_code'])}, {cell(row['seconds'])}s. See guest.log/update.log in diagnostics.")
    if not records:
        lines += ["", "**No acceptance records available. Inspect job logs; no guest checks can be certified.**"]
    lines += ["", "<details><summary>All recorded acceptance checks</summary>", "",
              "| Target | Phase | Check | Result | Seconds | Exit |", "|---|---|---|---|---:|---:|"]
    for row in records:
        lines.append("| " + " | ".join(cell(row[k]) for k in
                     ("target", "phase", "name", "status", "seconds", "exit_code")) + " |")
    lines += ["", "</details>", "", "## Warnings and coverage gaps", ""]
    for problem in problems:
        lines.append(f"- {cell(problem)}")
    warnings = collections.Counter()
    for path in sorted(root.rglob("guest.log")):
        for line in path.read_text(errors="replace").splitlines():
            if "[WARN]" in line or "warning:" in line.lower() or "suspicious line(s)" in line:
                warnings[line.strip()] += 1
    if warnings:
        lines += ["", "<details><summary>Guest warnings and shell-log assessments (occurrence counts)</summary>", ""]
        for message, count in warnings.most_common(40):
            lines.append(f"- {count}× {cell(message)}")
        if len(warnings) > 40:
            lines.append(f"- {len(warnings) - 40} additional distinct messages remain in guest.log.")
        lines += ["", "</details>", ""]
    lines += [
        "- WinApps inside Omarchy: preparation is dry-run only; upgraded Hyprland/RemoteApp integration is UNVERIFIED.",
        "- Windows job: direct FreeRDP/Notepad/Edge on Ubuntu/Xvfb; it does not exercise the installed WinApps launcher.",
        "- Radar preview clicks, Spaces interaction, animation smoothness, physical monitors and account login: UNVERIFIED.",
        "- Desktop groups contain IPC/layer checks, screenshots and selected OCR assertions; screenshots alone are not visual approval.",
        "- Updater uses a CI terminal adapter: preserved log and sudo TTY, bounded status refresh, harness-owned reboot.",
        "- Inspect artifacts for full logs, screenshots, actual versions and package inventories.",
    ]
    server = environment.get("GITHUB_SERVER_URL", "https://github.com")
    repo = environment.get("GITHUB_REPOSITORY", "")
    run = environment.get("GITHUB_RUN_ID", "")
    if repo and run:
        lines += ["", f"[Job logs and downloadable diagnostics]({server}/{repo}/actions/runs/{run})"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    output = render(Path(sys.argv[1]), os.environ)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(output)
