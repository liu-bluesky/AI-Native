#!/usr/bin/env bash
set -euo pipefail

# 只执行发布的 remote 阶段：
# - 在服务器做预检查、加锁、备份
# - offline 模式下执行 docker load；remote-build 模式下执行远程 docker build
# - 最后执行 deploy.sh up / deploy.sh deploy / rollback
# 默认开启 --update-db；可通过 DEPLOY_UPDATE_DB=false 关闭
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_DB="${DEPLOY_UPDATE_DB:-true}"

ARGS=(--stage remote)
if [[ "$UPDATE_DB" == "true" ]]; then
  ARGS+=(--update-db)
fi

exec python3 "$SCRIPT_DIR/remote_docker_deploy.py" "${ARGS[@]}" "$@"
