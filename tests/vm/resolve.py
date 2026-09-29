"""Resolve official releases; never silently substitute a different ISO."""
import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen


def version(value):
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError(f"not a stable Omarchy release: {value!r}")
    return tuple(map(int, value.removeprefix("v").split(".")))


def fetch(url):
    headers = {"User-Agent": "omarchy-setup-ci"}
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urlopen(Request(url, headers=headers), timeout=60) as response:
        return response.read().decode()


def plan(config, mode, latest):
    if mode not in {"pinned", "upgrade", "latest"}:
        raise ValueError(f"unknown VM mode: {mode}")
    pinned = config["baseline"]
    version(pinned)
    candidate = pinned if mode == "pinned" else latest.removeprefix("v")
    version(candidate)
    return {
        "mode": mode, "baseline": pinned, "candidate": candidate,
        "run": mode == "pinned" or version(candidate) > version(pinned),
        "install_version": candidate if mode == "latest" else pinned,
        "harness_commit": config["harness_commit"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("pinned", "upgrade", "latest"))
    parser.add_argument("--candidate", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(Path(__file__).with_name("releases.json").read_text())
    release = json.loads(fetch("https://api.github.com/repos/omacom/omarchy/releases/latest")) if args.mode != "pinned" else {"tag_name": config["baseline"]}
    latest = release["tag_name"]
    if args.candidate and version(args.candidate) != version(latest):
        raise ValueError("requested candidate is no longer the latest release; rerun discovery")
    result = plan(config, args.mode, latest)
    if result["run"]:
        name = f'omarchy-{result["install_version"]}.iso'
        url = f"https://iso.omarchy.org/{name}"
        parts = fetch(url + ".sha256").split()
        if not parts:
            raise ValueError("empty official ISO checksum")
        checksum = parts[0].lower()
        if not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
            raise ValueError("invalid official ISO checksum")
        if result["install_version"] == config["baseline"] and checksum != config["baseline_iso_sha256"]:
            raise ValueError("official baseline checksum differs from reviewed checksum")
        tag = "v" + result["install_version"]
        ref = json.loads(fetch(f"https://api.github.com/repos/omacom/omarchy/commits/{tag}"))
        result.update(iso_url=url, iso_name=name, iso_sha256=checksum, upstream_commit=ref["sha"])
        if args.mode == "upgrade":
            target = json.loads(fetch(f'https://api.github.com/repos/omacom/omarchy/commits/v{result["candidate"]}'))
            result["candidate_commit"] = target["sha"]
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key, value in result.items():
                print(f"{key}={str(value).lower() if isinstance(value, bool) else value}", file=output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
