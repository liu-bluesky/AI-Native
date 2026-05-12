#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REGISTRY="${REGISTRY:-docker.io}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-ai-employee}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH="${PUSH:-false}"
LOAD="${LOAD:-false}"

API_IMAGE="${API_IMAGE:-${REGISTRY}/${IMAGE_NAMESPACE}/ai-employee-api:${IMAGE_TAG}}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-${REGISTRY}/${IMAGE_NAMESPACE}/ai-employee-frontend:${IMAGE_TAG}}"

usage() {
  cat <<'EOF'
Usage:
  ./build-publish-images.sh [build|push|build-push|print]

Environment variables:
  REGISTRY=docker.io
  IMAGE_NAMESPACE=<dockerhub-user-or-org>
  IMAGE_TAG=latest
  PLATFORMS=linux/amd64,linux/arm64
  API_IMAGE=<full-api-image>               # optional override
  FRONTEND_IMAGE=<full-frontend-image>     # optional override
  PUSH=true|false                          # push after buildx build
  LOAD=true|false                          # load local single-platform image, incompatible with multi-platform push

Examples:
  IMAGE_NAMESPACE=mydockerhub IMAGE_TAG=v1.0.0 ./build-publish-images.sh build-push
  IMAGE_NAMESPACE=mydockerhub IMAGE_TAG=v1.0.0 PLATFORMS=linux/amd64 LOAD=true ./build-publish-images.sh build
  API_IMAGE=registry.example.com/team/ai-employee-api:v1 FRONTEND_IMAGE=registry.example.com/team/ai-employee-frontend:v1 ./build-publish-images.sh push
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

print_images() {
  cat <<EOF
API_IMAGE=$API_IMAGE
FRONTEND_IMAGE=$FRONTEND_IMAGE
IMAGE_TAG=$IMAGE_TAG
PLATFORMS=$PLATFORMS
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
