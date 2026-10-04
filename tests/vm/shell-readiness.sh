#!/bin/bash

# Retry only the transient IPC error emitted while Omarchy Shell is starting.
wait_for_shell() {
  local attempts=${1:-50} delay=${2:-0.3} attempt output

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if output=$(omarchy-shell shell ping 2>&1); then
      return 0
    fi

    case "$output" in
      *'omarchy-shell is not responding'*)
        if ((attempt == attempts)); then
          printf 'Omarchy Shell did not become ready after %s attempts: %s\n' \
            "$attempts" "$output" >&2
          return 1
        fi
        printf 'Waiting for Omarchy Shell IPC (%s/%s)\n' "$attempt" "$attempts" >&2
        sleep "$delay"
        ;;
      *)
        printf '%s\n' "$output" >&2
        return 1
        ;;
    esac
  done
}
