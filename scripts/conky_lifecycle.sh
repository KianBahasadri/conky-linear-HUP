#!/usr/bin/env bash

# Shared process and log-file primitives for the Conky launcher scripts.
# Callers are responsible for user-facing logging.

classify_fetch_loop_pid() {
  local pid_file="$1"
  local expected_script="$2"
  local project_root="$3"

  FETCH_LOOP_PID=""
  # Exported to the launcher that sourced this helper.
  # shellcheck disable=SC2034
  FETCH_LOOP_PID_STATUS="missing"

  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  FETCH_LOOP_PID="$(<"$pid_file")"
  if [[ ! "$FETCH_LOOP_PID" =~ ^[0-9]+$ ]]; then
    FETCH_LOOP_PID_STATUS="invalid"
    return 0
  fi
  if ! kill -0 "$FETCH_LOOP_PID" 2>/dev/null; then
    FETCH_LOOP_PID_STATUS="dead"
    return 0
  fi
  if ! fetch_loop_pid_is_owned "$FETCH_LOOP_PID" "$expected_script" "$project_root"; then
    FETCH_LOOP_PID_STATUS="foreign"
    return 0
  fi

  # Consumed by the sourcing launcher.
  # shellcheck disable=SC2034
  FETCH_LOOP_PID_STATUS="owned"
}

fetch_loop_pid_is_owned() {
  local pid="$1"
  local expected_script="$2"
  local project_root="$3"
  local pgid
  local -a command_line=()

  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  [[ -r "/proc/$pid/cmdline" ]] || return 1
  mapfile -d '' -t command_line < "/proc/$pid/cmdline" || return 1
  # The literal $8 is part of the child loop signature.
  # shellcheck disable=SC2016
  if (( ${#command_line[@]} < 12 )) \
      || [[ "${command_line[0]##*/}" != "bash" ]] \
      || [[ "${command_line[1]}" != "-c" ]] \
      || [[ "${command_line[2]}" != *'project_root="$8"'* ]] \
      || [[ "${command_line[2]}" != *"while true"* ]] \
      || [[ "${command_line[3]}" != "bash" ]] \
      || [[ "${command_line[4]}" != "$expected_script" ]] \
      || [[ "${command_line[11]}" != "$project_root" ]]; then
    return 1
  fi

  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null || true)"
  pgid="${pgid//[[:space:]]/}"
  [[ "$pgid" == "$pid" ]]
}

matching_fetch_loop_pids() {
  local expected_script="$1"
  local project_root="$2"
  local proc_path
  local pid

  for proc_path in /proc/[0-9]*; do
    pid="${proc_path##*/}"
    if fetch_loop_pid_is_owned "$pid" "$expected_script" "$project_root"; then
      printf '%s\n' "$pid"
    fi
  done
}

terminate_fetch_loop_pid() {
  local pid="$1"
  local expected_script="$2"
  local project_root="$3"
  local attempt

  # Consumed by the sourcing launcher.
  # shellcheck disable=SC2034
  FETCH_LOOP_FORCED_KILL=0
  fetch_loop_pid_is_owned "$pid" "$expected_script" "$project_root" || return 0
  kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || return 0
  for ((attempt = 0; attempt < 50; attempt++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.02
  done

  # Revalidate immediately before escalating so PID reuse can never turn a
  # stale process-list entry into SIGKILL against an unrelated process.
  if fetch_loop_pid_is_owned "$pid" "$expected_script" "$project_root"; then
    kill -KILL -- -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    # Consumed by the sourcing launcher.
    # shellcheck disable=SC2034
    FETCH_LOOP_FORCED_KILL=1
  fi
}

conky_pid_matches_config() {
  local pid="$1"
  local target="$2"
  local match_mode="${3:-exact}"
  local executable
  local config_path=""
  local index
  local -a command_line=()

  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  [[ -r "/proc/$pid/cmdline" ]] || return 1
  mapfile -d '' -t command_line < "/proc/$pid/cmdline" || return 1
  (( ${#command_line[@]} >= 3 )) || return 1
  [[ "${command_line[0]##*/}" == "conky" ]] || return 1
  for ((index = 1; index + 1 < ${#command_line[@]}; index++)); do
    if [[ "${command_line[$index]}" == "-c" ]]; then
      config_path="${command_line[$((index + 1))]}"
      break
    fi
  done
  [[ -n "$config_path" ]] || return 1

  case "$match_mode" in
    exact) [[ "$config_path" == "$target" ]] ;;
    prefix) [[ "$config_path" == "$target"* && "$config_path" == *.conkyrc ]] ;;
    *) return 1 ;;
  esac || return 1

  # Resolve the executable only after the cheap argv/config checks. A desktop
  # can have hundreds of processes, while only our Conky candidates need the
  # external readlink call.
  executable="$(readlink -f -- "/proc/$pid/exe" 2>/dev/null)" || return 1
  [[ "${executable##*/}" == "conky" ]]
}

matching_conky_pids() {
  local target="$1"
  local match_mode="${2:-exact}"
  local proc_path
  local pid

  for proc_path in /proc/[0-9]*; do
    pid="${proc_path##*/}"
    if conky_pid_matches_config "$pid" "$target" "$match_mode"; then
      printf '%s\n' "$pid"
    fi
  done
}

terminate_matching_conky_processes() {
  local target="$1"
  local match_mode="${2:-exact}"
  local attempt
  local pid
  local still_running
  local -a matching_pids=()

  mapfile -t matching_pids < <(matching_conky_pids "$target" "$match_mode")
  (( ${#matching_pids[@]} > 0 )) || return 0

  for pid in "${matching_pids[@]}"; do
    if conky_pid_matches_config "$pid" "$target" "$match_mode"; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  for ((attempt = 0; attempt < 50; attempt++)); do
    still_running=0
    for pid in "${matching_pids[@]}"; do
      if conky_pid_matches_config "$pid" "$target" "$match_mode"; then
        still_running=1
        break
      fi
    done
    (( still_running == 0 )) && return 0
    sleep 0.02
  done

  # Revalidate every PID immediately before escalation. A reused PID or a
  # process whose argv changed is never signaled as if it were still ours.
  for pid in "${matching_pids[@]}"; do
    if conky_pid_matches_config "$pid" "$target" "$match_mode"; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
}

rotate_log_file() {
  local log_path="$1"
  local max_bytes="$2"
  local rotations="$3"
  local size
  local generation
  local archived_path
  local archived_generation
  local temporary_path

  # Retention can be lowered independently of whether the current log is large
  # enough to rotate. Remove obsolete numeric generations on every check.
  for archived_path in "$log_path".[0-9]*; do
    [[ -e "$archived_path" ]] || continue
    archived_generation="${archived_path##*.}"
    [[ "$archived_generation" =~ ^[0-9]+$ ]] || continue
    if (( archived_generation > rotations )); then
      rm -f -- "$archived_path"
    fi
  done

  [[ -f "$log_path" ]] || return 1
  size="$(stat -c '%s' -- "$log_path" 2>/dev/null || true)"
  [[ "$size" =~ ^[0-9]+$ ]] || return 1
  (( size >= max_bytes )) || return 1

  temporary_path="$log_path.rotate.$$"
  if (( size > max_bytes )); then
    # Keep the recent tail, then discard its first (possibly partial) line so
    # a rotation never starts with the back half of a log record.
    if ! LC_ALL=C tail -c "$max_bytes" -- "$log_path" \
        | sed '1d' > "$temporary_path"; then
      rm -f -- "$temporary_path"
      return 1
    fi
    chmod --reference="$log_path" "$temporary_path" 2>/dev/null || true
  fi

  rm -f -- "$log_path.$rotations"
  for ((generation = rotations - 1; generation >= 1; generation--)); do
    if [[ -f "$log_path.$generation" ]]; then
      mv -f -- "$log_path.$generation" "$log_path.$((generation + 1))"
    fi
  done
  if (( size > max_bytes )); then
    mv -f -- "$temporary_path" "$log_path.1"
    rm -f -- "$log_path"
  else
    mv -f -- "$log_path" "$log_path.1"
  fi
}
