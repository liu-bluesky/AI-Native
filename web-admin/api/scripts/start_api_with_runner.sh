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

RUNNER_PORT_EXPLICIT=0
if [[ -n "${AGENT_RUNNER_PORT+x}" ]]; then
  RUNNER_PORT_EXPLICIT=1
fi

RUNNER_HOST="${AGENT_RUNNER_HOST:-127.0.0.1}"
RUNNER_PORT="${AGENT_RUNNER_PORT:-3931}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
RUNNER_URL="http://${RUNNER_HOST}:${RUNNER_PORT}"
RUNNER_LOG="${AGENT_RUNNER_LOG:-/tmp/agent-runner-${RUNNER_PORT}.log}"
API_PROBE_HOST="${API_PROBE_HOST:-127.0.0.1}"
API_URL="http://${API_PROBE_HOST}:${API_PORT}"

cd "${API_DIR}"

refresh_runner_runtime() {
  RUNNER_URL="http://${RUNNER_HOST}:${RUNNER_PORT}"
  RUNNER_LOG="${AGENT_RUNNER_LOG:-/tmp/agent-runner-${RUNNER_PORT}.log}"
}

refresh_api_runtime() {
  API_URL="http://${API_PROBE_HOST}:${API_PORT}"
}

runner_pid_on_port() {
  local port="${1:-${RUNNER_PORT}}"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n 1
}

runner_command_for_pid() {
  local pid="$1"
  ps -p "${pid}" -o command= 2>/dev/null || true
}

api_pid_on_port() {
  lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1
}

api_command_for_pid() {
  local pid="$1"
  ps -p "${pid}" -o command= 2>/dev/null || true
}

wait_runner_health() {
  local attempts="${1:-20}"
  for _ in $(seq 1 "${attempts}"); do
    if check_runner; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

stop_stale_runner() {
  local pid="$1"
  local cmd
  cmd="$(runner_command_for_pid "${pid}")"
  if [[ -z "${cmd}" ]]; then
    return 1
  fi
  if [[ "${cmd}" != *"scripts/agent_runner.py"* ]]; then
    echo "[runner] port ${RUNNER_PORT} is already used by another process:" >&2
    echo "[runner] ${pid} ${cmd}" >&2
    return 1
  fi

  echo "[runner] found stale runner on ${RUNNER_URL}, stopping pid ${pid}"
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
  done

  echo "[runner] pid ${pid} did not exit after SIGTERM, forcing shutdown"
  kill -9 "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  echo "[runner] failed to stop stale runner pid ${pid}" >&2
  return 1
}

check_runner() {
  curl -sS --max-time 2 "${RUNNER_URL}/health" >/dev/null 2>&1
}

check_api() {
  curl -sS --max-time 2 "${API_URL}/api/init/status" >/dev/null 2>&1
}

pick_fallback_runner_port() {
  local start_port="${RUNNER_PORT}"
  local candidate
  for candidate in $(seq $((start_port + 1)) $((start_port + 20))); do
    if [[ -z "$(runner_pid_on_port "${candidate}")" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

start_runner() {
  if check_runner; then
    echo "[runner] already healthy at ${RUNNER_URL}"
    return
  fi

  local pid=""
  pid="$(runner_pid_on_port || true)"
  if [[ -n "${pid}" ]]; then
    if ! stop_stale_runner "${pid}"; then
      if [[ "${RUNNER_PORT_EXPLICIT}" == "1" ]]; then
        exit 1
      fi
      local fallback_port=""
      fallback_port="$(pick_fallback_runner_port || true)"
      if [[ -z "${fallback_port}" ]]; then
        echo "[runner] no free fallback port available near ${RUNNER_PORT}" >&2
        exit 1
      fi
      echo "[runner] switching to fallback port ${fallback_port}"
      RUNNER_PORT="${fallback_port}"
      refresh_runner_runtime
    fi
  fi

  echo "[runner] starting at ${RUNNER_URL}"
  nohup env AGENT_RUNNER_HOST="${RUNNER_HOST}" AGENT_RUNNER_PORT="${RUNNER_PORT}" \
    python scripts/agent_runner.py >"${RUNNER_LOG}" 2>&1 &

  if wait_runner_health 20; then
    echo "[runner] healthy"
    return
  fi

  echo "[runner] failed to start, check log: ${RUNNER_LOG}" >&2
  tail -n 40 "${RUNNER_LOG}" >&2 || true
  exit 1
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

start_runner

prepare_api

echo "[api] EXTERNAL_AGENT_RUNNER_URL=${RUNNER_URL}"
echo "[api] starting uvicorn on ${API_HOST}:${API_PORT}"
exec env EXTERNAL_AGENT_RUNNER_URL="${RUNNER_URL}" \
  uvicorn server:app --host "${API_HOST}" --port "${API_PORT}"
