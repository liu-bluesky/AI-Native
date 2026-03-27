#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_DB="${DEPLOY_UPDATE_DB:-true}"

ARGS=(--stage remote)
if [[ "$UPDATE_DB" == "true" ]]; then
  ARGS+=(--update-db)
fi

exec python3 "$SCRIPT_DIR/remote_docker_deploy.py" "${ARGS[@]}" "$@"
