#!/bin/bash

# Retry only the transient IPC error emitted while Omarchy Shell is starting.
wait_for_shell() {
  local attempts=${1:-50} delay=${2:-0.3} attempt output

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if output=$(omarchy-shell shell ping 2>&1); then
      return 0
    fi

    case "$output" in
      *'omarchy-shell is not responding'*|*'omarchy-shell is not running'*)
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

wait_for_shell_path() {
  local attempts=${1:-50} delay=${2:-0.3} attempt output path

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if output=$(quickshell list --all 2>&1); then
      path=$(sed -n 's/^ *Config path: \(.*\)\/shell\/shell.qml$/\1/p' <<<"$output" | tail -1)
      if [[ -n $path ]]; then
        printf '%s\n' "$path"
        return 0
      fi
      output='active Omarchy Shell path is not listed yet'
    elif [[ $output != *'omarchy-shell is not responding'* && $output != *'omarchy-shell is not running'* ]]; then
      printf '%s\n' "$output" >&2
      return 1
    fi

    if ((attempt == attempts)); then
      printf 'Omarchy Shell path did not become available after %s attempts: %s\n' \
        "$attempts" "$output" >&2
      return 1
    fi
    printf 'Waiting for Omarchy Shell discovery (%s/%s)\n' "$attempt" "$attempts" >&2
    sleep "$delay"
  done
}
