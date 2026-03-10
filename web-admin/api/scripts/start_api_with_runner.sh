#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUNNER_HOST="${AGENT_RUNNER_HOST:-127.0.0.1}"
RUNNER_PORT="${AGENT_RUNNER_PORT:-3931}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
RUNNER_URL="http://${RUNNER_HOST}:${RUNNER_PORT}"
RUNNER_LOG="${AGENT_RUNNER_LOG:-/tmp/agent-runner-${RUNNER_PORT}.log}"

cd "${API_DIR}"

check_runner() {
  curl -sS --max-time 2 "${RUNNER_URL}/health" >/dev/null 2>&1
}

start_runner() {
  if check_runner; then
    echo "[runner] already healthy at ${RUNNER_URL}"
    return
  fi

  echo "[runner] starting at ${RUNNER_URL}"
  nohup env AGENT_RUNNER_HOST="${RUNNER_HOST}" AGENT_RUNNER_PORT="${RUNNER_PORT}" \
    python scripts/agent_runner.py >"${RUNNER_LOG}" 2>&1 &

  for _ in $(seq 1 20); do
    if check_runner; then
      echo "[runner] healthy"
      return
    fi
    sleep 0.5
  done

  echo "[runner] failed to start, check log: ${RUNNER_LOG}" >&2
  tail -n 40 "${RUNNER_LOG}" >&2 || true
  exit 1
}

start_runner

echo "[api] EXTERNAL_AGENT_RUNNER_URL=${RUNNER_URL}"
echo "[api] starting uvicorn on ${API_HOST}:${API_PORT}"
exec env EXTERNAL_AGENT_RUNNER_URL="${RUNNER_URL}" \
  uvicorn server:app --host "${API_HOST}" --port "${API_PORT}"
