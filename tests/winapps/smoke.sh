#!/usr/bin/env bash
set -euo pipefail

[[ ${GITHUB_ACTIONS:-} == true ]] || { echo "Refusing non-GitHub host"; exit 1; }
[[ -r /dev/kvm && -w /dev/kvm ]] || { echo "Direct KVM is unavailable"; exit 1; }

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${WINAPPS_ARTIFACTS:?}
SOURCE=${RUNNER_TEMP:?}/winapps-source
CONFIG=${HOME}/.config/winapps
IMAGE=$(PYTHONPATH="$ROOT/src" python -c 'from omarchy_setup.modules.programs import WINDOWS_IMAGE; print(WINDOWS_IMAGE)')
REVISION=$(PYTHONPATH="$ROOT/src" python -c 'from omarchy_setup.modules.programs import WINAPPS_REVISION; print(WINAPPS_REVISION)')
XVFB_PID=
READY_FILE=${HOME}/.local/share/winapps/ci-rdp-ready
mkdir -p "$ARTIFACTS" "$CONFIG"

cleanup() {
  status=$?
  trap - EXIT
  if [[ -n $XVFB_PID ]]; then
    kill "$XVFB_PID" 2>/dev/null || true
  fi
  podman logs WinApps >"$ARTIFACTS/windows-container.log" 2>&1 || true
  podman-compose --file "$CONFIG/compose.yaml" down --volumes >/dev/null 2>&1 || true
  rm -f "$READY_FILE" "$CONFIG/credentials.env"
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
printf 'USERNAME=winapps-ci\nPASSWORD=%s\n' "$WINAPPS_CI_PASSWORD" \
  >"$CONFIG/credentials.env"
chmod 0600 "$CONFIG/credentials.env" "$CONFIG/winapps.conf" "$CONFIG/compose.yaml"

export WINAPPS_RAM_SIZE=4G WINAPPS_CPU_CORES=2 WINAPPS_DISK_SIZE=64G
export WINAPPS_AUTOLOGIN=N
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

freerdp_args() {
  printf '%s\n' \
    '/v:127.0.0.1:3389' \
    '/u:winapps-ci' \
    "/p:${WINAPPS_CI_PASSWORD}" \
    '/d:' \
    '/cert:ignore' \
    '/scale:100' \
    '+auto-reconnect' \
    "$@"
}

mkdir -p "$(dirname "$READY_FILE")"
READY_WINDOWS='\\tsclient\home\.local\share\winapps\ci-rdp-ready'
echo "Waiting for an authenticated RemoteApp command"
ready=0
for attempt in $(seq 1 36); do
  rm -f "$READY_FILE"
  if timeout 30s "$FREERDP" /args-from:fd:3 \
      3< <(freerdp_args '+home-drive' \
        "/app:program:C:\Windows\System32\cmd.exe,hidef:on,cmd:/C type NUL > ${READY_WINDOWS} && tsdiscon") \
      >"$ARTIFACTS/rdp-readiness.log" 2>&1; then
    :
  fi
  if [[ -f $READY_FILE ]]; then
    ready=1
    break
  fi
  echo "  Windows RemoteApp command is not ready (attempt $attempt/36)"
  if (( attempt % 3 == 0 )); then
    podman logs --tail 8 WinApps 2>&1 | sed -E 's/(PASSWORD=)[^ ]+/\1[redacted]/g'
  fi
  sleep 20
done
[[ $ready == 1 ]] || { echo "Authenticated RemoteApp did not become ready"; exit 1; }
echo "RemoteApp command succeeded; waiting for its session to terminate"
sleep 25

open_remoteapp() {
  name=$1
  executable=$2
  expected_title=$3
  log="$ARTIFACTS/${name}.log"
  window=''
  for launch_attempt in $(seq 1 6); do
    echo "Opening $name RemoteApp (attempt $launch_attempt/6)"
    "$FREERDP" /args-from:fd:3 \
      3< <(freerdp_args "/wm-class:${name}" \
        "/app:program:${executable},hidef:on,name:${name}") \
      >>"$log" 2>&1 &
    pid=$!
    for _ in $(seq 1 30); do
      while read -r candidate; do
        title=$(xdotool getwindowname "$candidate" 2>/dev/null || true)
        if [[ $title =~ $expected_title ]]; then
          window=$candidate
          break
        fi
      done < <(xdotool search --onlyvisible --pid "$pid" 2>/dev/null || true)
      [[ -n $window ]] && break 2
      kill -0 "$pid" 2>/dev/null || break
      sleep 2
    done
    xwininfo -root -tree >"$ARTIFACTS/${name}-windows-${launch_attempt}.txt" 2>&1 || true
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

open_remoteapp notepad 'C:\Windows\System32\notepad.exe' '[Nn]otepad'
open_remoteapp edge 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' '([Ee]dge|Microsoft Edge)'

if cmp -s "$ARTIFACTS/notepad.png" "$ARTIFACTS/edge.png"; then
  echo 'Notepad and Edge evidence images are unexpectedly identical'
  exit 1
fi

printf '%s\n' \
  'PASS: built-in Notepad and Edge mapped as RemoteApp windows.' \
  'Office, licensed applications, Dropbox, and physical displays were not tested.' \
  | tee "$ARTIFACTS/result.txt"
