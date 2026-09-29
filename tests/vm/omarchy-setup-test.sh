#!/bin/bash

set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SETUP_ROOT=$(cd -- "$TEST_DIR/../omarchy-setup" && pwd)
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-setup"
LAUNCHER="$HOME/.local/bin/omarchy-setup"

export PYTHONDONTWRITEBYTECODE=1

SUDO_ASKPASS_DIR=""
cleanup() {
  sudo -k 2>/dev/null || true
  if [[ -n $SUDO_ASKPASS_DIR && -d $SUDO_ASKPASS_DIR ]]; then
    rm -rf -- "$SUDO_ASKPASS_DIR"
  fi
}
trap cleanup EXIT

echo "==> bootstrap from fresh checkout"
"$SETUP_ROOT/omarchy-setup" init -y --quiet
[[ -x $STATE_ROOT/environment/bin/python ]]
[[ -L $LAUNCHER ]]
"$LAUNCHER" --version

echo "==> verify idempotent init"
environment_inode=$(stat -c %i "$STATE_ROOT/environment")
"$LAUNCHER" init -y --quiet
[[ $(stat -c %i "$STATE_ROOT/environment") == "$environment_inode" ]]

echo "==> run repository tests with managed Python"
PYTHONPATH="$SETUP_ROOT/src" "$STATE_ROOT/environment/bin/python" \
  -m unittest discover -s "$SETUP_ROOT/tests" -v

echo "==> plan deblob against fresh Omarchy package state"
"$LAUNCHER" deblob -y --quiet --dry-run --config "$TEST_DIR/deblob.toml"

echo "==> install all optional programs without login onboarding"
if ! sudo -n -v 2>/dev/null; then
  [[ -n ${OMARCHY_ACCEPTANCE_SUDO_PASSWORD:-} ]] || {
    echo "not ok - program installation needs non-interactive sudo" >&2
    exit 1
  }
  SUDO_ASKPASS_DIR=$(mktemp -d /tmp/omarchy-setup-askpass.XXXXXX)
  SUDO_ASKPASS="$SUDO_ASKPASS_DIR/askpass"
  export SUDO_ASKPASS
  printf '%s\n' '#!/bin/sh' 'printf "%s\\n" "$OMARCHY_ACCEPTANCE_SUDO_PASSWORD"' >"$SUDO_ASKPASS"
  chmod 0700 "$SUDO_ASKPASS"
  sudo -A -v
fi
"$LAUNCHER" install all -y -d --quiet
[[ -x "$HOME/.local/share/omarchy-setup/miniforge3/bin/mamba" ]]
grep -Fq '# >>> omarchy-setup mamba >>>' "$HOME/.bashrc"

echo "==> verify idempotent optional program installation"
"$LAUNCHER" install all -y --quiet

echo "ok - bootstrap, program installation, and deblob plan passed"
