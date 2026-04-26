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
API_REUSE_HEALTHY="${API_REUSE_HEALTHY:-0}"
FEISHU_WORKER_ENABLED="${FEISHU_WORKER_ENABLED:-1}"
FEISHU_WORKER_CONNECTOR_IDS="${FEISHU_WORKER_CONNECTOR_IDS:-feishu-main}"
API_RUNTIME_DIR="${API_RUNTIME_DIR:-${API_DIR}/.runtime}"
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

python_bin() {
  if [[ -x "${API_DIR}/.venv/bin/python" ]]; then
    echo "${API_DIR}/.venv/bin/python"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  command -v python3
}

feishu_worker_pid_for_connector() {
  local connector_id="$1"
  pgrep -f "feishu_long_connection_worker.py --connector-id ${connector_id}" 2>/dev/null | head -n 1 || true
}

stop_feishu_worker_pid() {
  local pid="$1"
  if [[ -z "${pid}" ]]; then
    return 0
  fi
  echo "[feishu-worker] stopping stale pid ${pid}"
  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.3
  done
  echo "[feishu-worker] forcing stale pid ${pid}"
  kill -9 "${pid}" 2>/dev/null || true
}

start_feishu_workers() {
  if [[ "${FEISHU_WORKER_ENABLED}" != "1" ]]; then
    echo "[feishu-worker] disabled by FEISHU_WORKER_ENABLED=${FEISHU_WORKER_ENABLED}"
    return 0
  fi
  mkdir -p "${API_RUNTIME_DIR}/logs" "${API_RUNTIME_DIR}/pids"
  local py
  py="$(python_bin)"
  local connector_id
  for connector_id in ${FEISHU_WORKER_CONNECTOR_IDS//,/ }; do
    connector_id="${connector_id//[[:space:]]/}"
    [[ -z "${connector_id}" ]] && continue
    local existing_pid=""
    existing_pid="$(feishu_worker_pid_for_connector "${connector_id}" || true)"
    if [[ -n "${existing_pid}" ]]; then
      echo "[feishu-worker] already running for ${connector_id} (pid ${existing_pid})"
      echo "${existing_pid}" > "${API_RUNTIME_DIR}/pids/feishu-worker-${connector_id}.pid"
      continue
    fi
    local log_file="${API_RUNTIME_DIR}/logs/feishu-worker-${connector_id}.log"
    echo "[feishu-worker] starting connector ${connector_id}"
    nohup "${py}" "${API_DIR}/scripts/feishu_long_connection_worker.py" --connector-id "${connector_id}" >> "${log_file}" 2>&1 &
    local worker_pid="$!"
    echo "${worker_pid}" > "${API_RUNTIME_DIR}/pids/feishu-worker-${connector_id}.pid"
    echo "[feishu-worker] started pid ${worker_pid}, log: ${log_file}"
  done
}

stop_feishu_workers() {
  local connector_id
  for connector_id in ${FEISHU_WORKER_CONNECTOR_IDS//,/ }; do
    connector_id="${connector_id//[[:space:]]/}"
    [[ -z "${connector_id}" ]] && continue
    local pid=""
    pid="$(feishu_worker_pid_for_connector "${connector_id}" || true)"
    stop_feishu_worker_pid "${pid}"
  done
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
      if [[ "${API_REUSE_HEALTHY}" == "1" ]]; then
        echo "[api] already healthy at ${API_URL}"
        echo "[api] reusing pid ${pid}: ${cmd}"
        start_feishu_workers
        exit 0
      fi
      echo "[api] healthy api detected at ${API_URL}, restarting pid ${pid}"
      stop_feishu_workers
      stop_stale_api "${pid}" || exit 1
      return
    fi
    echo "[api] already healthy at ${API_URL}, but no local pid was found; skipping restart"
    start_feishu_workers
    exit 0
  fi

  local pid=""
  pid="$(api_pid_on_port || true)"
  if [[ -n "${pid}" ]]; then
    stop_feishu_workers
    stop_stale_api "${pid}" || exit 1
  fi
}

prepare_api
start_feishu_workers

echo "[api] runner disabled: start_api_with_runner.sh starts API and Feishu workers"
echo "[api] starting uvicorn on ${API_HOST}:${API_PORT}"
if command -v uv >/dev/null 2>&1; then
  exec env EXTERNAL_AGENT_RUNNER_URL="" \
    uv run python -m uvicorn server:app --host "${API_HOST}" --port "${API_PORT}"
fi

exec env EXTERNAL_AGENT_RUNNER_URL="" \
  uvicorn server:app --host "${API_HOST}" --port "${API_PORT}"
