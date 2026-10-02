#!/usr/bin/env bash
set -euo pipefail

[[ ${GITHUB_ACTIONS:-} == true ]] || { echo "Refusing non-GitHub host"; exit 1; }
[[ -r /dev/kvm && -w /dev/kvm ]] || { echo "Direct KVM is unavailable"; exit 1; }

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${WINAPPS_ARTIFACTS:?}
SOURCE=${RUNNER_TEMP:?}/winapps-source
ASKPASS=${RUNNER_TEMP}/winapps-askpass
CONFIG=${HOME}/.config/winapps
IMAGE=$(PYTHONPATH="$ROOT/src" python -c 'from omarchy_setup.modules.programs import WINDOWS_IMAGE; print(WINDOWS_IMAGE)')
REVISION=$(PYTHONPATH="$ROOT/src" python -c 'from omarchy_setup.modules.programs import WINAPPS_REVISION; print(WINAPPS_REVISION)')
XVFB_PID=
mkdir -p "$ARTIFACTS" "$CONFIG"

cleanup() {
  status=$?
  trap - EXIT
  if [[ -n $XVFB_PID ]]; then
    kill "$XVFB_PID" 2>/dev/null || true
  fi
  podman logs WinApps >"$ARTIFACTS/windows-container.log" 2>&1 || true
  podman-compose --file "$CONFIG/compose.yaml" down --volumes >/dev/null 2>&1 || true
  rm -f "$ASKPASS" "$CONFIG/credentials.env"
  exit "$status"
}
trap cleanup EXIT

git clone --filter=blob:none --no-checkout https://github.com/winapps-org/winapps.git "$SOURCE"
git -C "$SOURCE" fetch --depth=1 origin "$REVISION"
git -C "$SOURCE" checkout --detach "$REVISION"
git -C "$SOURCE" rev-parse HEAD >"$ARTIFACTS/winapps-revision.txt"
cp "$ROOT/programs/winapps/templates/compose.yaml" "$CONFIG/compose.yaml"
cp "$ROOT/programs/winapps/templates/winapps.conf" "$CONFIG/winapps.conf"
cp -a "$SOURCE/oem" "$CONFIG/oem"

WINAPPS_CI_PASSWORD=$(openssl rand -hex 24)
export WINAPPS_CI_PASSWORD
cat >"$ASKPASS" <<'EOF'
#!/bin/sh
printf '%s\n' "$WINAPPS_CI_PASSWORD"
EOF
chmod 0700 "$ASKPASS"
printf 'USERNAME=winapps-ci\nPASSWORD=%s\n' "$WINAPPS_CI_PASSWORD" \
  >"$CONFIG/credentials.env"
chmod 0600 "$CONFIG/credentials.env" "$CONFIG/winapps.conf" "$CONFIG/compose.yaml"

export WINAPPS_RAM_SIZE=4G WINAPPS_CPU_CORES=2 WINAPPS_DISK_SIZE=64G
podman pull "$IMAGE"
podman image inspect "$IMAGE" --format '{{.Digest}}' \
  >"$ARTIFACTS/windows-image-digest.txt"
podman-compose --file "$CONFIG/compose.yaml" up --detach

export DISPLAY=:99
Xvfb "$DISPLAY" -screen 0 1920x1080x24 >"$ARTIFACTS/xvfb.log" 2>&1 &
XVFB_PID=$!
sleep 2

FREERDP=$(command -v xfreerdp3 || command -v xfreerdp)
"$FREERDP" /version >"$ARTIFACTS/freerdp-version.txt" 2>&1

echo "Waiting for authenticated Windows RDP readiness"
ready=0
for attempt in $(seq 1 36); do
  if "$ASKPASS" | timeout 30s "$FREERDP" \
      /v:127.0.0.1:3389 /u:winapps-ci /cert:ignore /from-stdin /auth-only \
      >"$ARTIFACTS/rdp-readiness.log" 2>&1; then
    ready=1
    break
  fi
  echo "  Windows is not ready for authentication (attempt $attempt/36)"
  if (( attempt % 3 == 0 )); then
    podman logs --tail 8 WinApps 2>&1 | sed -E 's/(PASSWORD=)[^ ]+/\1[redacted]/g'
  fi
  sleep 20
done
[[ $ready == 1 ]] || { echo "Authenticated RDP did not become ready"; exit 1; }

open_remoteapp() {
  name=$1
  executable=$2
  log="$ARTIFACTS/${name}.log"
  window=''
  for launch_attempt in $(seq 1 6); do
    echo "Opening $name RemoteApp (attempt $launch_attempt/6)"
    "$ASKPASS" | "$FREERDP" \
      /v:127.0.0.1:3389 /u:winapps-ci /cert:ignore \
      /from-stdin /size:1280x800 /app:program:"$executable",name:"$name" \
      >>"$log" 2>&1 &
    pid=$!
    for _ in $(seq 1 30); do
      window=$(xdotool search --onlyvisible --pid "$pid" 2>/dev/null | head -1 || true)
      [[ -n $window ]] && break 2
      kill -0 "$pid" 2>/dev/null || break
      sleep 2
    done
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    sleep 20
  done
  [[ -n $window ]] || { echo "$name RemoteApp did not map a window"; return 1; }
  xdotool getwindowname "$window" >"$ARTIFACTS/${name}-window-title.txt"
  import -window "$window" "$ARTIFACTS/${name}.png"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

open_remoteapp notepad 'C:\Windows\System32\notepad.exe'
open_remoteapp edge 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

printf '%s\n' \
  'PASS: built-in Notepad and Edge mapped as RemoteApp windows.' \
  'Office, licensed applications, Dropbox, and physical displays were not tested.' \
  | tee "$ARTIFACTS/result.txt"
