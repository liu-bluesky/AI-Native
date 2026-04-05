#!/usr/bin/env bash
set -euo pipefail

# 只执行发布的 package 阶段：
# - offline 模式下，本地构建 API / Frontend 镜像并 docker save 成 tar
# - remote-build 模式下，本地打源码包
# 不会连接服务器，也不会执行远程部署
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$SCRIPT_DIR/remote_docker_deploy.py" --stage package "$@"
