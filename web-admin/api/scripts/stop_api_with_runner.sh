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

RUNNER_HOST="${AGENT_RUNNER_HOST:-127.0.0.1}"
RUNNER_PORT="${AGENT_RUNNER_PORT:-3931}"
API_PORT="${API_PORT:-8000}"
RUNNER_URL="http://${RUNNER_HOST}:${RUNNER_PORT}"
RUNNER_LOG="${AGENT_RUNNER_LOG:-/tmp/agent-runner-${RUNNER_PORT}.log}"

FORCE=0
if [[ "${1:-}" == "-f" || "${1:-}" == "--force" ]]; then
  FORCE=1
fi

runner_pid_on_port() {
  local port="${1:-${RUNNER_PORT}}"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n 1
}

runner_pid_by_cmd() {
  pgrep -f "scripts/agent_runner.py" 2>/dev/null || true
}

api_pid_on_port() {
  lsof -tiTCP:"${API_PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1
}

api_pid_by_cmd() {
  pgrep -f "uvicorn server:app" 2>/dev/null || true
}

stop_api() {
  local pid="${1:-}"
  if [[ -z "${pid}" ]]; then
    echo "[api] no API process found"
    return 0
  fi

  echo "[api] stopping process (pid: ${pid})..."
  kill "${pid}" 2>/dev/null || true

  if [[ "${FORCE}" == "1" ]]; then
    sleep 0.5
    if kill -0 "${pid}" 2>/dev/null; then
      echo "[api] forcing shutdown (pid: ${pid})..."
      kill -9 "${pid}" 2>/dev/null || true
    fi
  else
    for _ in $(seq 1 10); do
      if ! kill -0 "${pid}" 2>/dev/null; then
        echo "[api] stopped"
        return 0
      fi
      sleep 0.5
    done
    echo "[api] did not exit after SIGTERM, use -f to force"
    return 1
  fi

  if kill -0 "${pid}" 2>/dev/null; then
    echo "[api] failed to stop pid ${pid}"
    return 1
  else
    echo "[api] stopped"
  fi
}

stop_runner() {
  local pid="${1:-}"
  if [[ -z "${pid}" ]]; then
    echo "[runner] no runner process found"
    return 0
  fi

  echo "[runner] stopping process (pid: ${pid})..."
  kill "${pid}" 2>/dev/null || true

  if [[ "${FORCE}" == "1" ]]; then
    sleep 0.5
    if kill -0 "${pid}" 2>/dev/null; then
      echo "[runner] forcing shutdown (pid: ${pid})..."
      kill -9 "${pid}" 2>/dev/null || true
    fi
  else
    for _ in $(seq 1 10); do
      if ! kill -0 "${pid}" 2>/dev/null; then
        echo "[runner] stopped"
        return 0
      fi
      sleep 0.5
    done
    echo "[runner] did not exit after SIGTERM, use -f to force"
    return 1
  fi

  if kill -0 "${pid}" 2>/dev/null; then
    echo "[runner] failed to stop pid ${pid}"
    return 1
  else
    echo "[runner] stopped"
  fi
}

cleanup_log() {
  if [[ -f "${RUNNER_LOG}" ]]; then
    rm -f "${RUNNER_LOG}"
    echo "[runner] log file removed: ${RUNNER_LOG}"
  fi
}

echo "=== Stopping API and Runner ==="
echo ""

API_PID=""
RUNNER_PID=""

# Find API process
API_PID_BY_PORT="$(api_pid_on_port || true)"
API_PID_BY_CMD="$(api_pid_by_cmd || true)"

if [[ -n "${API_PID_BY_PORT}" ]]; then
  API_PID="${API_PID_BY_PORT}"
  echo "[api] found on port ${API_PORT} (pid: ${API_PID})"
elif [[ -n "${API_PID_BY_CMD}" ]]; then
  API_PID="${API_PID_BY_CMD}"
  echo "[api] found by command (pid: ${API_PID})"
fi

# Find Runner process
RUNNER_PID_BY_PORT="$(runner_pid_on_port || true)"
RUNNER_PID_BY_CMD="$(runner_pid_by_cmd || true)"

if [[ -n "${RUNNER_PID_BY_PORT}" ]]; then
  RUNNER_PID="${RUNNER_PID_BY_PORT}"
  echo "[runner] found on port ${RUNNER_PORT} (pid: ${RUNNER_PID})"
elif [[ -n "${RUNNER_PID_BY_CMD}" ]]; then
  RUNNER_PID="${RUNNER_PID_BY_CMD}"
  echo "[runner] found by command (pid: ${RUNNER_PID})"
fi

echo ""

# Stop services in reverse order: API first, then Runner
if [[ -n "${API_PID}" ]]; then
  stop_api "${API_PID}"
fi

if [[ -n "${RUNNER_PID}" ]]; then
  stop_runner "${RUNNER_PID}"
fi

cleanup_log

echo ""
echo "=== All services stopped ==="
