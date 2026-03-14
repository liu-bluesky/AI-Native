#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${LOCAL_CONNECTOR_HOST:-127.0.0.1}"
PORT="${LOCAL_CONNECTOR_PORT:-3931}"
export LOCAL_CONNECTOR_HOST="$HOST"
export LOCAL_CONNECTOR_PORT="$PORT"

if ! command -v node >/dev/null 2>&1; then
  echo "未检测到 Node.js，请先安装 Node.js 18 或更高版本。"
  echo "下载地址：https://nodejs.org/"
  exit 1
fi

exec node launcher.js
