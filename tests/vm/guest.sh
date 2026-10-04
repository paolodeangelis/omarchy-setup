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
KEEPALIVE=''
CURRENT_STEP=''
STEP_STARTED=0
record_step() {
  jq -cn --arg target "$MODE" --arg phase "$PHASE" --arg name "$CURRENT_STEP" \
    --arg status "$1" --argjson exit_code "$2" --argjson seconds "$((SECONDS - STEP_STARTED))" \
    '{target:$target,phase:$phase,name:$name,status:$status,exit_code:$exit_code,seconds:$seconds}' \
    >> "$ARTIFACTS/results-$PHASE.jsonl"
}
step() {
  CURRENT_STEP=$1
  shift
  STEP_STARTED=$SECONDS
  echo "==> [$MODE/$PHASE] $CURRENT_STEP"
  "$@"
  record_step PASS 0
  CURRENT_STEP=''
}
cleanup() {
  result=$?
  trap - EXIT
  if [[ -n $CURRENT_STEP ]]; then
    record_step FAIL "$result" || true
  fi
  CURRENT_STEP='Phase completion (includes ungrouped assertions)'
  STEP_STARTED=$SECONDS
  if (( result == 0 )); then
    record_step PASS 0 || true
  else
    record_step FAIL "$result" || true
  fi
  if [[ -f /tmp/omarchy-update.log ]]; then
    cp /tmp/omarchy-update.log "$ARTIFACTS/update.log" || true
  fi
  [[ -z $KEEPALIVE ]] || kill "$KEEPALIVE" 2>/dev/null || true
  journalctl --user -b -t omarchy-shell --no-pager > "$ARTIFACTS/shell-$PHASE.log" 2>&1 || true
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
  printf '%s\n' "$actual" >> "$ARTIFACTS/version-$PHASE.txt"
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
  "$STATE_ROOT/environment/bin/python" "$SETUP_ROOT/tests/vm/desktop.py" "$ARTIFACTS/$stage"
  [[ -z $(hyprctl configerrors) ]]
}
agent_hooks_configured() {
  local wrapper="$STATE_ROOT/bin/omarchy-spaces-agent"
  local reporter="$HOME/.config/omarchy/plugins/tornikegomareli.spaces/hooks/claude-hook"
  [[ -x $wrapper && -x $reporter ]]
  jq -e --arg command "$wrapper waiting" '
    [.hooks.PermissionRequest[].hooks[]
      | select(.type == "command" and .command == $command and .async == false)]
    | length == 1
  ' "$HOME/.codex/hooks.json" >/dev/null
  jq -e --arg command "$wrapper end" '
    [.hooks.Interrupt[].hooks[] | select(.type == "command") | .command]
    | index($command) != null
  ' "$HOME/.codex/hooks.json" >/dev/null
  jq -e --arg command "$wrapper waiting" '
    [.hooks.Notification[].hooks[] | select(.type == "command") | .command]
    | index($command) != null
  ' "$HOME/.claude/settings.json" >/dev/null
  printf '{"session_id":"ci-spaces-hook-smoke"}\n' | "$wrapper" waiting
  printf '{"session_id":"ci-spaces-hook-smoke"}\n' | "$wrapper" end
}
update_system() {
  timeout --kill-after=30s 2400 "$STATE_ROOT/environment/bin/python" \
    "$SETUP_ROOT/tests/vm/update.py" </dev/null 2>&1 | tee /tmp/omarchy-update.log
}
if [[ $PHASE == initial ]]; then
  step 'Installed baseline version' check_version "$(jq -r .install_version "$VM_TEST_DIR/run.json")"
  session
  # The official harness already proved installation and boot. Preserve one
  # stock screenshot and readiness check; do not make this utility's result
  # depend on unrelated live-data/product acceptance such as weather content.
  [[ $OMARCHY_PATH == /usr/share/omarchy ]]
  grim "$ARTIFACTS/stock-desktop.png"
  [[ ! -e $SETUP_ROOT ]] || { echo 'Guest checkout must start absent'; exit 1; }
  cp -a "$SOURCE_ROOT" "$SETUP_ROOT"
  step 'Bootstrap' "$SETUP_ROOT/omarchy-setup" init -y --no-progress
  authorize
  environment_inode=$(stat -c %i "$STATE_ROOT/environment")
  step 'Repeat bootstrap' "$LAUNCHER" init -y --no-progress
  [[ $(stat -c %i "$STATE_ROOT/environment") == "$environment_inode" ]]
  step 'Guest unit and integration suite' env PYTHONPATH="$SETUP_ROOT/src" "$STATE_ROOT/environment/bin/python" -m unittest discover -s "$SETUP_ROOT/tests" -t "$SETUP_ROOT" -v
  step 'Install programs and defaults' "$LAUNCHER" install all -y -d --no-progress
  step 'WinApps preparation plan only' "$LAUNCHER" install winapps -y --install-only --dry-run --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-before-repeat.txt"
  step 'Repeat program installation' "$LAUNCHER" install all -y -d --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-after-repeat.txt"
  step 'Program package idempotency' cmp "$ARTIFACTS/packages-before-repeat.txt" "$ARTIFACTS/packages-after-repeat.txt"
  sequence=0
  for style in fixed floating fixed; do
    sequence=$((sequence + 1))
    step "Theme $sequence/$style" "$LAUNCHER" theme "bar-$style" -y --no-progress
    step "Agent hook configuration $sequence/$style" agent_hooks_configured
    step "Desktop checks $sequence/$style" checks "$sequence-$style"
    cp "$STATE_ROOT/themes/olio-su-silicio/state.json" "$ARTIFACTS/state-before.json"
    "$LAUNCHER" theme "bar-$style" -y --no-progress
    step "Theme idempotency $sequence/$style" cmp "$ARTIFACTS/state-before.json" "$STATE_ROOT/themes/olio-su-silicio/state.json"
  done
  step 'Restore stock theme' "$LAUNCHER" theme restore -y --no-progress
  session
  [[ $OMARCHY_PATH == /usr/share/omarchy ]]
  omarchy-shell shell summon omarchy.menu '{}'
  sleep 1
  grim "$ARTIFACTS/restored-menu.png"
  omarchy-shell shell hide omarchy.menu
  "$LAUNCHER" theme bar-fixed -y --no-progress
  session
  step 'Deblob plan' "$LAUNCHER" deblob -y --dry-run --no-progress
  step 'Deblob apply' "$LAUNCHER" deblob -y --no-progress
  step 'Deblob repeat' "$LAUNCHER" deblob -y --no-progress
  step 'Configured desktop checks' checks configured
  if [[ $MODE == upgrade ]]; then
    # Do not reapply our setup before checking the upgraded installation.
    step 'Configured baseline version before update' check_version "$(jq -r .install_version "$VM_TEST_DIR/run.json")"
    # Preserve the exact log consumed by upstream analysis; pipefail preserves
    # updater errors. The harness reboots only after successful completion.
    step 'Official system update (CI terminal adapter)' update_system
    cp /tmp/omarchy-update.log "$ARTIFACTS/update.log"
    step 'Installed candidate version' check_version "$(jq -r .candidate "$VM_TEST_DIR/run.json")"
  fi
elif [[ $PHASE == post-upgrade && $MODE == upgrade ]]; then
  step 'Candidate version after reboot' check_version "$(jq -r .candidate "$VM_TEST_DIR/run.json")"
  UPSTREAM_TESTS="$UPSTREAM_TESTS/candidate/test"
  authorize
  step 'Desktop after reboot before reapply' checks after-upgrade-before-reapply
  sequence=0
  for style in fixed floating fixed; do
    sequence=$((sequence + 1))
    step "Theme $sequence/$style" "$LAUNCHER" theme "bar-$style" -y --no-progress
    step "Agent hook configuration $sequence/$style" agent_hooks_configured
    step "Desktop checks $sequence/$style" checks "after-upgrade-$sequence-$style"
    cp "$STATE_ROOT/themes/olio-su-silicio/state.json" "$ARTIFACTS/state-before-post-upgrade.json"
    "$LAUNCHER" theme "bar-$style" -y --no-progress
    step "Theme idempotency $sequence/$style" cmp "$ARTIFACTS/state-before-post-upgrade.json" "$STATE_ROOT/themes/olio-su-silicio/state.json"
  done
  step 'Restore stock theme' "$LAUNCHER" theme restore -y --no-progress
  session
  [[ $OMARCHY_PATH == /usr/share/omarchy ]]
  omarchy-shell shell summon omarchy.menu '{}'
  sleep 1
  grim "$ARTIFACTS/restored-menu-post-upgrade.png"
  omarchy-shell shell hide omarchy.menu
  "$LAUNCHER" theme bar-fixed -y --no-progress
  session
  step 'Post-upgrade program installation' "$LAUNCHER" install all -y --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-post-upgrade-before-repeat.txt"
  step 'Repeat program installation' "$LAUNCHER" install all -y --no-progress
  pacman -Q | sort > "$ARTIFACTS/packages-post-upgrade-after-repeat.txt"
  step 'Program package idempotency' cmp "$ARTIFACTS/packages-post-upgrade-before-repeat.txt" "$ARTIFACTS/packages-post-upgrade-after-repeat.txt"
  step 'WinApps preparation plan only' "$LAUNCHER" install winapps -y --install-only --dry-run --no-progress
  step 'Deblob plan' "$LAUNCHER" deblob -y --dry-run --no-progress
  step 'Deblob apply' "$LAUNCHER" deblob -y --no-progress
  step 'Deblob repeat' "$LAUNCHER" deblob -y --no-progress
  step 'Configured desktop checks after upgrade' checks after-upgrade-configured
  step 'Guest unit and integration suite after upgrade' env PYTHONPATH="$SETUP_ROOT/src" "$STATE_ROOT/environment/bin/python" -m unittest discover -s "$SETUP_ROOT/tests" -t "$SETUP_ROOT" -v
else
  echo "Invalid phase/mode $PHASE/$MODE"; exit 1
fi
echo "PASS: automated subset for $MODE $PHASE; radar preview, Spaces interactions and animation remain unverified"
