#!/bin/bash
# Invoked exclusively by the reviewed official ISO VM harness.
set -euo pipefail
VM_TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCE_ROOT=$(cd -- "$VM_TEST_DIR/../.." && pwd)
ARTIFACTS=/tmp/omarchy-acceptance/setup
mkdir -p "$ARTIFACTS"
exec > >(tee -a "$ARTIFACTS/guest.log") 2>&1
[[ $(id -u) != 0 && $(hostname) == omarchy-test ]] || { echo 'Refusing non-test host'; exit 1; }
systemd-detect-virt --vm >/dev/null
[[ -s "$VM_TEST_DIR/run.json" ]] || { echo 'Missing harness run manifest'; exit 1; }
PHASE=${1:?initial or post-upgrade}
MODE=$(jq -r .mode "$VM_TEST_DIR/run.json")
LAUNCHER="$HOME/.local/bin/omarchy-setup"
SETUP_ROOT="$HOME/.omarchy-setup"
STATE_ROOT="$HOME/.local/state/omarchy-setup"
UPSTREAM_TESTS=$(cd -- "$SOURCE_ROOT/.." && pwd)
STARTED=$(date --iso-8601=seconds)
KEEPALIVE=''
cleanup() {
  result=$?
  trap - EXIT
  [[ -z $KEEPALIVE ]] || kill "$KEEPALIVE" 2>/dev/null || true
  journalctl --user -t omarchy-shell --since "$STARTED" --no-pager > "$ARTIFACTS/shell-$PHASE.log" 2>&1 || true
  pacman -Q > "$ARTIFACTS/packages-$PHASE.txt" || true
  grim "$ARTIFACTS/final-$PHASE.png" || true
  printf '%s\n' "$result" > "$ARTIFACTS/exit-$PHASE.txt"
  sudo -k || true
  exit "$result"
}
trap cleanup EXIT
session() {
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
  while IFS='=' read -r key value; do
    case "$key" in WAYLAND_DISPLAY|HYPRLAND_INSTANCE_SIGNATURE|DISPLAY) export "$key=$value" ;; esac
  done < <(systemctl --user show-environment)
  hyprctl -j monitors | jq -e 'length > 0' >/dev/null
  export OMARCHY_PATH
  OMARCHY_PATH=$(quickshell list --all | sed -n 's/^ *Config path: \(.*\)\/shell\/shell.qml$/\1/p' | tail -1)
  [[ -n $OMARCHY_PATH ]]
  export QML2_IMPORT_PATH="$OMARCHY_PATH/shell"
  export PATH="$OMARCHY_PATH/bin:$HOME/.local/bin:$PATH"
  omarchy-shell shell ping
}
check_version() {
  local expected=$1 actual
  actual=$(omarchy version)
  printf '%s\n' "$actual" > "$ARTIFACTS/version-$PHASE.txt"
  [[ ${actual%%-*} == "$expected" ]] || { echo "Expected $expected; installed $actual"; exit 1; }
}
authorize() {
  export SUDO_ASKPASS="$SETUP_ROOT/tests/vm/askpass.sh"
  chmod 0700 "$SUDO_ASKPASS"
  sudo -A -v
  (while sleep 45; do sudo -n -v || exit; done) &
  KEEPALIVE=$!
}
checks() {
  local stage=$1
  session
  mkdir -p "$ARTIFACTS/$stage"
  "$LAUNCHER" doctor --ui
  "$STATE_ROOT/environment/bin/python" "$SETUP_ROOT/tests/vm/desktop.py" "$ARTIFACTS/$stage" "$STARTED"
  [[ -z $(hyprctl configerrors) ]]
}
agent_hooks_configured() {
  local wrapper="$STATE_ROOT/bin/omarchy-spaces-agent"
  local reporter="$HOME/.config/omarchy/plugins/tornikegomareli.spaces/hooks/claude-hook"
  [[ -x $wrapper && -x $reporter ]]
  jq -e --arg command "$wrapper $reporter waiting" '
    [.hooks.PermissionRequest[].hooks[] | select(.type == "command") | .command]
    | index($command) != null
  ' "$HOME/.codex/hooks.json" >/dev/null
  jq -e --arg command "$wrapper $reporter waiting" '
    [.hooks.Notification[].hooks[] | select(.type == "command") | .command]
    | index($command) != null
  ' "$HOME/.claude/settings.json" >/dev/null
}
if [[ $PHASE == initial ]]; then
  check_version "$(jq -r .install_version "$VM_TEST_DIR/run.json")"
  session
  # The official harness already proved installation and boot. Preserve one
  # stock screenshot and readiness check; do not make this utility's result
  # depend on unrelated live-data/product acceptance such as weather content.
  [[ $OMARCHY_PATH == /usr/share/omarchy ]]
  grim "$ARTIFACTS/stock-desktop.png"
  [[ ! -e $SETUP_ROOT ]] || { echo 'Guest checkout must start absent'; exit 1; }
  cp -a "$SOURCE_ROOT" "$SETUP_ROOT"
  "$SETUP_ROOT/omarchy-setup" init -y --no-progress
  authorize
  environment_inode=$(stat -c %i "$STATE_ROOT/environment")
  "$LAUNCHER" init -y --no-progress
  [[ $(stat -c %i "$STATE_ROOT/environment") == "$environment_inode" ]]
  PYTHONPATH="$SETUP_ROOT/src" "$STATE_ROOT/environment/bin/python" -m unittest discover -s "$SETUP_ROOT/tests" -t "$SETUP_ROOT" -v
  "$LAUNCHER" install all -y -d --no-progress
  "$LAUNCHER" install winapps -y --install-only --dry-run --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-before-repeat.txt"
  "$LAUNCHER" install all -y -d --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-after-repeat.txt"
  cmp "$ARTIFACTS/packages-before-repeat.txt" "$ARTIFACTS/packages-after-repeat.txt"
  sequence=0
  for style in fixed floating fixed; do
    sequence=$((sequence + 1))
    "$LAUNCHER" theme "bar-$style" -y --no-progress
    agent_hooks_configured
    checks "$sequence-$style"
    cp "$STATE_ROOT/themes/olio-su-silicio/state.json" "$ARTIFACTS/state-before.json"
    "$LAUNCHER" theme "bar-$style" -y --no-progress
    cmp "$ARTIFACTS/state-before.json" "$STATE_ROOT/themes/olio-su-silicio/state.json"
  done
  "$LAUNCHER" theme restore -y --no-progress
  session
  [[ $OMARCHY_PATH == /usr/share/omarchy ]]
  omarchy-shell shell summon omarchy.menu '{}'
  sleep 1
  grim "$ARTIFACTS/restored-menu.png"
  omarchy-shell shell hide omarchy.menu
  "$LAUNCHER" theme bar-fixed -y --no-progress
  session
  "$LAUNCHER" deblob -y --dry-run --no-progress
  "$LAUNCHER" deblob -y --no-progress
  "$LAUNCHER" deblob -y --no-progress
  checks configured
  if [[ $MODE == upgrade ]]; then
    # Do not reapply our setup before checking the upgraded installation.
    timeout 5400 omarchy update -y </dev/null
    check_version "$(jq -r .candidate "$VM_TEST_DIR/run.json")"
  fi
elif [[ $PHASE == post-upgrade && $MODE == upgrade ]]; then
  check_version "$(jq -r .candidate "$VM_TEST_DIR/run.json")"
  UPSTREAM_TESTS="$UPSTREAM_TESTS/candidate/test"
  authorize
  checks after-upgrade-before-reapply
  sequence=0
  for style in fixed floating fixed; do
    sequence=$((sequence + 1))
    "$LAUNCHER" theme "bar-$style" -y --no-progress
    agent_hooks_configured
    checks "after-upgrade-$sequence-$style"
    cp "$STATE_ROOT/themes/olio-su-silicio/state.json" "$ARTIFACTS/state-before-post-upgrade.json"
    "$LAUNCHER" theme "bar-$style" -y --no-progress
    cmp "$ARTIFACTS/state-before-post-upgrade.json" "$STATE_ROOT/themes/olio-su-silicio/state.json"
  done
  "$LAUNCHER" theme restore -y --no-progress
  session
  [[ $OMARCHY_PATH == /usr/share/omarchy ]]
  omarchy-shell shell summon omarchy.menu '{}'
  sleep 1
  grim "$ARTIFACTS/restored-menu-post-upgrade.png"
  omarchy-shell shell hide omarchy.menu
  "$LAUNCHER" theme bar-fixed -y --no-progress
  session
  "$LAUNCHER" install all -y --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-post-upgrade-before-repeat.txt"
  "$LAUNCHER" install all -y --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-post-upgrade-after-repeat.txt"
  cmp "$ARTIFACTS/packages-post-upgrade-before-repeat.txt" "$ARTIFACTS/packages-post-upgrade-after-repeat.txt"
  "$LAUNCHER" install winapps -y --install-only --dry-run --no-progress
  "$LAUNCHER" deblob -y --dry-run --no-progress
  "$LAUNCHER" deblob -y --no-progress
  "$LAUNCHER" deblob -y --no-progress
  checks after-upgrade-configured
  PYTHONPATH="$SETUP_ROOT/src" "$STATE_ROOT/environment/bin/python" -m unittest discover -s "$SETUP_ROOT/tests" -t "$SETUP_ROOT" -v
else
  echo "Invalid phase/mode $PHASE/$MODE"; exit 1
fi
echo "PASS: automated subset for $MODE $PHASE; radar preview, Spaces interactions and animation remain unverified"
