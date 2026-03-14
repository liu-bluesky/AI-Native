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

FORCE=0
if [[ "${1:-}" == "-f" || "${1:-}" == "--force" ]]; then
  FORCE=1
fi

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

echo "=== Stopping API ==="
echo ""

API_PID=""

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

# Stop API only
if [[ -n "${API_PID}" ]]; then
  stop_api "${API_PID}"
fi

echo ""
echo "=== API stopped ==="
