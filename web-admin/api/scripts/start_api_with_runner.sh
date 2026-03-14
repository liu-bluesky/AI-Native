#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

load_env_defaults() {
  local env_file="$1"
  if [[ ! -f "${env_file}" ]]; then
    return
  fi
  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    local line="${raw_line#"${raw_line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    [[ "${line}" == export\ * ]] && line="${line#export }"
    [[ "${line}" != *=* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    key="${key#"${key%%[![:space:]]*}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "${value}" =~ ^\".*\"$ || "${value}" =~ ^\'.*\'$ ]]; then
      value="${value:1:${#value}-2}"
    fi
    if [[ -z "${!key+x}" ]]; then
      export "${key}=${value}"
    fi
  done < "${env_file}"
}

load_env_defaults "${API_DIR}/.env"
load_env_defaults "${API_DIR}/.env.local"

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
API_PROBE_HOST="${API_PROBE_HOST:-127.0.0.1}"
API_URL="http://${API_PROBE_HOST}:${API_PORT}"

cd "${API_DIR}"

refresh_api_runtime() {
  API_URL="http://${API_PROBE_HOST}:${API_PORT}"
}

api_pid_on_port() {
  lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1
}

api_command_for_pid() {
  local pid="$1"
  ps -p "${pid}" -o command= 2>/dev/null || true
}


check_api() {
  curl -sS --max-time 2 "${API_URL}/api/init/status" >/dev/null 2>&1
}

stop_stale_api() {
  local pid="$1"
  local cmd
  cmd="$(api_command_for_pid "${pid}")"
  if [[ -z "${cmd}" ]]; then
    return 1
  fi
  if [[ "${cmd}" != *"uvicorn server:app"* ]]; then
    echo "[api] port ${API_PORT} is already used by another process:" >&2
    echo "[api] ${pid} ${cmd}" >&2
    return 1
  fi

  echo "[api] found stale api on ${API_URL}, stopping pid ${pid}"
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
  done

  echo "[api] pid ${pid} did not exit after SIGTERM, forcing shutdown"
  kill -9 "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  echo "[api] failed to stop stale api pid ${pid}" >&2
  return 1
}

prepare_api() {
  refresh_api_runtime
  if check_api; then
    local pid=""
    pid="$(api_pid_on_port || true)"
    if [[ -n "${pid}" ]]; then
      local cmd=""
      cmd="$(api_command_for_pid "${pid}")"
      echo "[api] already healthy at ${API_URL}"
      echo "[api] reusing pid ${pid}: ${cmd}"
      exit 0
    fi
    echo "[api] already healthy at ${API_URL}"
    exit 0
  fi

  local pid=""
  pid="$(api_pid_on_port || true)"
  if [[ -n "${pid}" ]]; then
    stop_stale_api "${pid}" || exit 1
  fi
}

prepare_api

echo "[api] runner disabled: start_api_with_runner.sh now starts API only"
echo "[api] starting uvicorn on ${API_HOST}:${API_PORT}"
exec env EXTERNAL_AGENT_RUNNER_URL="" \
  uvicorn server:app --host "${API_HOST}" --port "${API_PORT}"
