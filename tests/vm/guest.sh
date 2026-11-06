#!/bin/bash
# Invoked exclusively by the reviewed official ISO VM harness.
set -euo pipefail
VM_TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCE_ROOT=$(cd -- "$VM_TEST_DIR/../.." && pwd)
source "$VM_TEST_DIR/shell-readiness.sh"
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
CURRENT_CATEGORY=core
STEP_STARTED=0
record_step() {
  jq -cn --arg target "$MODE" --arg phase "$PHASE" --arg name "$CURRENT_STEP" \
    --arg status "$1" --argjson exit_code "$2" --argjson seconds "$((SECONDS - STEP_STARTED))" \
    --arg category "$CURRENT_CATEGORY" \
    '{target:$target,phase:$phase,category:$category,name:$name,status:$status,exit_code:$exit_code,seconds:$seconds}' \
    >> "$ARTIFACTS/results-$PHASE.jsonl"
}
step() {
  CURRENT_CATEGORY=core
  CURRENT_STEP=$1
  shift
  STEP_STARTED=$SECONDS
  echo "==> [$MODE/$PHASE] $CURRENT_STEP"
  "$@"
  record_step PASS 0
  CURRENT_STEP=''
}
plugin_step() {
  CURRENT_CATEGORY=plugin
  CURRENT_STEP=$1
  shift
  STEP_STARTED=$SECONDS
  echo "==> [$MODE/$PHASE] $CURRENT_STEP (plugin check; failure deferred)"
  if "$@"; then
    record_step PASS 0
  else
    local result=$?
    record_step FAIL "$result"
  fi
  CURRENT_STEP=''
  CURRENT_CATEGORY=core
}
record_plugin_results() {
  local file=$1 plugin status error
  [[ -s $file ]] || return 0
  while IFS=$'\t' read -r plugin status error; do
    [[ $status == PASS ]] && continue
    CURRENT_STEP="Plugin rendering: $plugin"
    CURRENT_CATEGORY=plugin
    STEP_STARTED=$SECONDS
    echo "Plugin failure deferred: $plugin: $error" >&2
    record_step FAIL 1
    CURRENT_STEP=''
    CURRENT_CATEGORY=core
  done < <(jq -r '.[] | [.plugin, .status, .error] | @tsv' "$file")
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
  OMARCHY_PATH=$(wait_for_shell_path)
  export QML2_IMPORT_PATH="$OMARCHY_PATH/shell"
  export PATH="$OMARCHY_PATH/bin:$HOME/.local/bin:$PATH"
  wait_for_shell
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
  plugin_step "Doctor after plugin integration: $stage" "$LAUNCHER" doctor --ui
  "$STATE_ROOT/environment/bin/python" "$SETUP_ROOT/tests/vm/desktop.py" "$ARTIFACTS/$stage"
  record_plugin_results "$ARTIFACTS/$stage/plugin-results.json"
  [[ -z $(hyprctl configerrors) ]]
}
agent_hooks_configured() {
  local wrapper="$STATE_ROOT/bin/omarchy-spaces-agent" attempt
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
  for ((attempt = 1; attempt <= 30; attempt++)); do
    if printf '{"session_id":"ci-spaces-hook-smoke"}\n' | "$wrapper" waiting; then
      break
    fi
    if ((attempt == 30)); then
      echo 'Spaces agent IPC did not become ready after 15 seconds' >&2
      return 1
    fi
    sleep 0.5
  done
  printf '{"session_id":"ci-spaces-hook-smoke"}\n' | "$wrapper" end
}
zoom_native_configured() {
  local native="$HOME/.local/share/applications/Zoom.desktop"
  local web="$HOME/.local/share/applications/Zoom Web.desktop"
  pacman -Q zoom >/dev/null
  [[ -f $native && -f $web ]]
  rg -q '^Exec=.*zoom' "$native"
  ! rg -q 'omarchy-webapp-handler-zoom' "$native"
  rg -q 'omarchy-webapp-handler-zoom' "$web"
  [[ $(xdg-mime query default x-scheme-handler/zoommtg) == Zoom.desktop ]]
  [[ $(xdg-mime query default x-scheme-handler/zoomus) == Zoom.desktop ]]
}
program_plans() {
  local program
  while read -r program; do
    "$LAUNCHER" install "$program" -y --dry-run --no-progress
  done < <(
    PYTHONPATH="$SETUP_ROOT/src" "$STATE_ROOT/environment/bin/python" -c \
      'from omarchy_setup.modules.programs import PROGRAMS; print(*[p.name for p in PROGRAMS if p.include_in_all and p.flatpak_id is None], sep="\n")'
  )
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
  step 'Program plans on baseline' program_plans
  step 'WinApps preparation plan only' "$LAUNCHER" install winapps -y --install-only --dry-run --no-progress
  step 'Core doctor before plugins' "$LAUNCHER" doctor --ui
  plugin_step 'Managed plugins' "$LAUNCHER" plugin apply -y --no-progress
  plugin_step 'Managed plugin status' "$LAUNCHER" plugin status
  sequence=0
  for style in fixed floating fixed; do
    sequence=$((sequence + 1))
    step "Theme $sequence/$style" "$LAUNCHER" theme "bar-$style" -y --no-progress
    plugin_step "Agent hook configuration $sequence/$style" agent_hooks_configured
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
  plugin_step 'Managed plugins after upgrade' "$LAUNCHER" plugin apply -y --no-progress
  plugin_step 'Managed plugin status after upgrade' "$LAUNCHER" plugin status
  sequence=0
  for style in fixed floating fixed; do
    sequence=$((sequence + 1))
    step "Theme $sequence/$style" "$LAUNCHER" theme "bar-$style" -y --no-progress
    plugin_step "Agent hook configuration $sequence/$style" agent_hooks_configured
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
  step 'Install Flatpak prerequisite after upgrade' omarchy pkg add flatpak
  step 'Configure Flathub prerequisite after upgrade' flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
  step 'Post-upgrade program installation' "$LAUNCHER" install all -y -d --no-progress
  step 'Managed upgrade source report after upgrade' "$LAUNCHER" upgrade all --check --source
  step 'Native Zoom integration after upgrade' zoom_native_configured
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
if jq -s -e 'any(.[]; .category == "plugin" and .status == "FAIL")' \
    "$ARTIFACTS"/results-*.jsonl >/dev/null; then
  if [[ $MODE == upgrade && $PHASE == initial ]]; then
    echo 'WARN: plugin failures recorded; continuing to the upgrade and final checks' >&2
  else
    echo 'FAIL: core acceptance completed, but one or more plugin checks failed' >&2
    CURRENT_CATEGORY=plugin
    exit 1
  fi
fi
echo "PASS: automated subset for $MODE $PHASE; radar preview, Spaces interactions and animation remain unverified"
