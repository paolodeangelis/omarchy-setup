#!/bin/bash

set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SETUP_ROOT=$(cd -- "$TEST_DIR/../omarchy-setup" && pwd)
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-setup"
LAUNCHER="$HOME/.local/bin/omarchy-setup"

export PYTHONDONTWRITEBYTECODE=1

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

echo "ok - omarchy-setup bootstrap and deblob plan passed"
