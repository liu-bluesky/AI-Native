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

API_PORT="${API_PORT:-8000}"
FEISHU_WORKER_CONNECTOR_IDS="${FEISHU_WORKER_CONNECTOR_IDS:-feishu-main}"
API_RUNTIME_DIR="${API_RUNTIME_DIR:-${API_DIR}/.runtime}"

FORCE=0
if [[ "${1:-}" == "-f" || "${1:-}" == "--force" ]]; then
  FORCE=1
fi

api_pid_on_port() {
  lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN 2>/dev/null || true
}

api_pid_by_cmd() {
  pgrep -f "${API_DIR}.*uvicorn server:app" 2>/dev/null || true
}

feishu_worker_pids_for_connector() {
  local connector_id="$1"
  pgrep -f "${API_DIR}/scripts/feishu_long_connection_worker.py --connector-id ${connector_id}" 2>/dev/null || true
}

start_script_pids() {
  pgrep -f "${API_DIR}/scripts/start_api_with_runner.sh" 2>/dev/null || true
}

unique_pids() {
  awk 'NF && !seen[$1]++ { print $1 }'
}

stop_pid() {
  local label="$1"
  local pid="$2"
  if [[ -z "${pid}" ]]; then
    return 0
  fi
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  echo "[${label}] stopping process (pid: ${pid})..."
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "[${label}] stopped"
      return 0
    fi
    sleep 0.3
  done
  if [[ "${FORCE}" != "1" ]]; then
    echo "[${label}] did not exit after SIGTERM, forcing shutdown (pid: ${pid})..."
  else
    echo "[${label}] forcing shutdown (pid: ${pid})..."
  fi
  kill -9 "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "[${label}] stopped"
      return 0
    fi
    sleep 0.2
  done
  echo "[${label}] pid ${pid} still appears alive after SIGKILL; continuing final verification"
  return 0
}

stop_feishu_workers() {
  local found=0
  local connector_id
  for connector_id in ${FEISHU_WORKER_CONNECTOR_IDS//,/ }; do
    connector_id="${connector_id//[[:space:]]/}"
    [[ -z "${connector_id}" ]] && continue
    local pids=""
    pids="$(feishu_worker_pids_for_connector "${connector_id}" || true)"
    if [[ -z "${pids}" ]]; then
      echo "[feishu-worker] no worker found for ${connector_id}"
      continue
    fi
    local pid
    for pid in ${pids}; do
      found=1
      stop_pid "feishu-worker" "${pid}"
    done
    rm -f "${API_RUNTIME_DIR}/pids/feishu-worker-${connector_id}.pid" 2>/dev/null || true
  done
  return 0
}

stop_start_scripts() {
  local pids=""
  pids="$(start_script_pids | unique_pids || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  local pid
  for pid in ${pids}; do
    [[ "${pid}" == "$$" ]] && continue
    stop_pid "runner" "${pid}"
  done
}

api_pids() {
  {
    api_pid_on_port
    api_pid_by_cmd
  } | unique_pids
}

stop_api() {
  local pids=""
  pids="$(api_pids || true)"
  if [[ -z "${pids}" ]]; then
    echo "[api] no API process found"
    return 0
  fi
  local pid
  for pid in ${pids}; do
    stop_pid "api" "${pid}"
  done
}

verify_stopped() {
  local remaining_api=""
  local remaining_workers=""
  remaining_api="$(api_pids || true)"
  local connector_id
  for connector_id in ${FEISHU_WORKER_CONNECTOR_IDS//,/ }; do
    connector_id="${connector_id//[[:space:]]/}"
    [[ -z "${connector_id}" ]] && continue
    remaining_workers+=$'\n'"$(feishu_worker_pids_for_connector "${connector_id}" || true)"
  done
  remaining_workers="$(printf "%s\n" "${remaining_workers}" | unique_pids || true)"
  if [[ -n "${remaining_api}" || -n "${remaining_workers}" ]]; then
    echo "[stop] remaining project processes detected:" >&2
    [[ -n "${remaining_api}" ]] && echo "[stop] api pids: ${remaining_api}" >&2
    [[ -n "${remaining_workers}" ]] && echo "[stop] feishu worker pids: ${remaining_workers}" >&2
    return 1
  fi
  return 0
}

echo "=== Stopping API and Feishu workers ==="
echo ""

stop_start_scripts
stop_feishu_workers
stop_api
# API supervisor can spawn workers too, so run worker cleanup again after API stops.
stop_feishu_workers
verify_stopped

echo ""
echo "=== API and Feishu workers stopped ==="
