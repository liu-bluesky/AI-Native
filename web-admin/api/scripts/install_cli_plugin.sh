#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ID="${1:-}"
CLI_PLUGIN_RUNTIME_PATH="${CLI_PLUGIN_RUNTIME_PATH:-${PATH:-}}"
CLI_PLUGIN_NODE_PATH="${CLI_PLUGIN_NODE_PATH:-}"
CLI_PLUGIN_NPM_PATH="${CLI_PLUGIN_NPM_PATH:-}"
CLI_PLUGIN_NPX_PATH="${CLI_PLUGIN_NPX_PATH:-}"
CLI_PLUGIN_TOOLCHAIN_ROOT="${CLI_PLUGIN_TOOLCHAIN_ROOT:-}"
CLI_PLUGIN_TOOLCHAIN_BIN_DIR="${CLI_PLUGIN_TOOLCHAIN_BIN_DIR:-}"
CLI_PLUGIN_NPM_GLOBAL_PREFIX="${CLI_PLUGIN_NPM_GLOBAL_PREFIX:-}"

if [[ -z "${PLUGIN_ID}" ]]; then
  echo "plugin_id is required" >&2
  exit 2
fi

if [[ -n "${CLI_PLUGIN_RUNTIME_PATH}" ]]; then
  export PATH="${CLI_PLUGIN_RUNTIME_PATH}"
fi

if [[ -n "${CLI_PLUGIN_NODE_PATH}" ]]; then
  export PATH="$(dirname "${CLI_PLUGIN_NODE_PATH}"):${PATH}"
fi

if [[ -n "${CLI_PLUGIN_TOOLCHAIN_BIN_DIR}" ]]; then
  mkdir -p "${CLI_PLUGIN_TOOLCHAIN_BIN_DIR}"
  export PATH="${CLI_PLUGIN_TOOLCHAIN_BIN_DIR}:${PATH}"
fi

if [[ -n "${CLI_PLUGIN_TOOLCHAIN_ROOT}" ]]; then
  mkdir -p "${CLI_PLUGIN_TOOLCHAIN_ROOT}"
fi

if [[ -n "${CLI_PLUGIN_NPM_GLOBAL_PREFIX}" ]]; then
  mkdir -p "${CLI_PLUGIN_NPM_GLOBAL_PREFIX}/bin"
  export NPM_CONFIG_PREFIX="${CLI_PLUGIN_NPM_GLOBAL_PREFIX}"
  export npm_config_prefix="${CLI_PLUGIN_NPM_GLOBAL_PREFIX}"
  export PATH="${CLI_PLUGIN_NPM_GLOBAL_PREFIX}/bin:${PATH}"
fi

NPX_BIN="${CLI_PLUGIN_NPX_PATH}"
if [[ -z "${NPX_BIN}" ]]; then
  NPX_BIN="$(command -v npx || true)"
fi

if [[ -z "${NPX_BIN}" || ! -x "${NPX_BIN}" ]]; then
  echo "npx is required but was not found in PATH" >&2
  exit 127
fi

case "${PLUGIN_ID}" in
  feishu-cli)
    exec "${NPX_BIN}" @larksuite/cli@latest install
    ;;
  *)
    echo "unsupported plugin_id: ${PLUGIN_ID}" >&2
    exit 2
    ;;
esac
