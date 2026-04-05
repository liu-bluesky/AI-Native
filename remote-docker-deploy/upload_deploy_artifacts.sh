#!/usr/bin/env bash
set -euo pipefail

# 只执行发布的 upload 阶段：
# - 检查本地 package 阶段产物是否存在
# - 通过 scp / ssh 把 tar 或源码包上传到远程服务器
# 不会在远程执行 docker load、docker build 或 deploy.sh up
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$SCRIPT_DIR/remote_docker_deploy.py" --stage upload "$@"
