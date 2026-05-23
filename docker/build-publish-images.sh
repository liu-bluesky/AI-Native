#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REGISTRY="${REGISTRY:-docker.io}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-ai-employee}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-ai-employee}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH="${PUSH:-false}"
LOAD="${LOAD:-false}"
VITE_SHOW_LOCAL_RUNTIME_SETTINGS="${VITE_SHOW_LOCAL_RUNTIME_SETTINGS:-false}"

# 默认采用“单仓库多 tag”发布方式：<registry>/<namespace>/<repo>:api-<tag> / frontend-<tag>
# 如需兼容旧的拆分仓库，可显式传 API_IMAGE / FRONTEND_IMAGE 覆盖。
IMAGE_PREFIX="${REGISTRY}/${IMAGE_NAMESPACE}/${IMAGE_REPOSITORY}"
API_IMAGE="${API_IMAGE:-${IMAGE_PREFIX}:api-${IMAGE_TAG}}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-${IMAGE_PREFIX}:frontend-${IMAGE_TAG}}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-${IMAGE_PREFIX}:postgres-17}"
REDIS_IMAGE="${REDIS_IMAGE:-${IMAGE_PREFIX}:redis-7-alpine}"

usage() {
  cat <<'EOF'
Usage:
  ./build-publish-images.sh [build|push|build-push|push-runtime|push-runtime-manifest|print]

Environment variables:
  REGISTRY=docker.io
  IMAGE_NAMESPACE=<dockerhub-user-or-org>
  IMAGE_REPOSITORY=ai-employee
  IMAGE_TAG=latest
  PLATFORMS=linux/amd64,linux/arm64
  API_IMAGE=<full-api-image>               # optional override
  FRONTEND_IMAGE=<full-frontend-image>     # optional override
  POSTGRES_IMAGE=<full-postgres-image>     # optional runtime image tag
  REDIS_IMAGE=<full-redis-image>           # optional runtime image tag
  VITE_SHOW_LOCAL_RUNTIME_SETTINGS=false   # frontend build arg
  PUSH=true|false                          # push after buildx build
  LOAD=true|false                          # load local single-platform image, incompatible with multi-platform push

Default image layout: single Docker Hub repository with component tags:
  docker.io/${IMAGE_NAMESPACE}/${IMAGE_REPOSITORY}:api-${IMAGE_TAG}
  docker.io/${IMAGE_NAMESPACE}/${IMAGE_REPOSITORY}:frontend-${IMAGE_TAG}
  docker.io/${IMAGE_NAMESPACE}/${IMAGE_REPOSITORY}:postgres-17
  docker.io/${IMAGE_NAMESPACE}/${IMAGE_REPOSITORY}:redis-7-alpine

Examples:
  IMAGE_NAMESPACE=lantianliu IMAGE_TAG=1.0.1 ./build-publish-images.sh build-push
  IMAGE_NAMESPACE=lantianliu IMAGE_TAG=1.0.1 ./build-publish-images.sh push-runtime-manifest
  IMAGE_NAMESPACE=lantianliu IMAGE_TAG=1.0.1 PLATFORMS=linux/amd64 LOAD=true ./build-publish-images.sh build
  API_IMAGE=registry.example.com/team/api:v1 FRONTEND_IMAGE=registry.example.com/team/frontend:v1 ./build-publish-images.sh push
EOF
}

ensure_buildx() {
  docker buildx version >/dev/null 2>&1 || {
    echo "docker buildx not available" >&2
    exit 1
  }
}

build_one() {
  local image="$1"
  local dockerfile="$2"
  local args=(buildx build "$PROJECT_ROOT" -f "$PROJECT_ROOT/$dockerfile" --platform "$PLATFORMS" -t "$image")
  if [[ "$dockerfile" == "docker/Dockerfile.frontend" ]]; then
    args+=(--build-arg "VITE_SHOW_LOCAL_RUNTIME_SETTINGS=$VITE_SHOW_LOCAL_RUNTIME_SETTINGS")
  fi
  if [[ "$PUSH" == "true" ]]; then
    args+=(--push)
  elif [[ "$LOAD" == "true" ]]; then
    if [[ "$PLATFORMS" == *","* ]]; then
      echo "LOAD=true only supports one platform. Set PLATFORMS=linux/amd64 or use PUSH=true." >&2
      exit 1
    fi
    args+=(--load)
  fi
  docker "${args[@]}"
}

push_runtime_images() {
  # 兼容旧流程：docker pull/tag/push 只会推送当前机器平台，不保证生成多架构 manifest。
  # 公开发布建议使用 push-runtime-manifest。
  docker pull postgres:17
  docker pull redis:7-alpine
  docker tag postgres:17 "$POSTGRES_IMAGE"
  docker tag redis:7-alpine "$REDIS_IMAGE"
  docker push "$POSTGRES_IMAGE"
  docker push "$REDIS_IMAGE"
}

push_runtime_manifests() {
  ensure_buildx
  docker buildx imagetools create -t "$POSTGRES_IMAGE" docker.io/library/postgres:17
  # Redis 官方 tag 有更多平台；这里显式聚合公开部署需要的 linux/amd64 与 linux/arm64，降低 registry 网络失败面。
  docker buildx imagetools create -t "$REDIS_IMAGE" \
    docker.io/library/redis:7-alpine@sha256:b1addbe72465a718643cff9e60a58e6df1841e29d6d7d60c9a85d8d72f08d1a7 \
    docker.io/library/redis:7-alpine@sha256:084f4bcb3fedf990ba43d26774f58ed4697a2c044156544ac4717934ad1d57c8
}

print_images() {
  cat <<EOF
API_IMAGE=$API_IMAGE
FRONTEND_IMAGE=$FRONTEND_IMAGE
POSTGRES_IMAGE=$POSTGRES_IMAGE
REDIS_IMAGE=$REDIS_IMAGE
IMAGE_TAG=$IMAGE_TAG
PLATFORMS=$PLATFORMS
VITE_SHOW_LOCAL_RUNTIME_SETTINGS=$VITE_SHOW_LOCAL_RUNTIME_SETTINGS
EOF
}

ACTION="${1:-build}"
case "$ACTION" in
  build)
    ensure_buildx
    PUSH=false
    build_one "$API_IMAGE" "docker/Dockerfile.api"
    build_one "$FRONTEND_IMAGE" "docker/Dockerfile.frontend"
    print_images
    ;;
  push)
    docker push "$API_IMAGE"
    docker push "$FRONTEND_IMAGE"
    print_images
    ;;
  build-push)
    ensure_buildx
    PUSH=true
    build_one "$API_IMAGE" "docker/Dockerfile.api"
    build_one "$FRONTEND_IMAGE" "docker/Dockerfile.frontend"
    print_images
    ;;
  push-runtime)
    push_runtime_images
    print_images
    ;;
  push-runtime-manifest)
    push_runtime_manifests
    print_images
    ;;
  print)
    print_images
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
