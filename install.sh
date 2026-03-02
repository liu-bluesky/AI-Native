#!/usr/bin/env bash
# rule-porter-mcp 规则安装脚本（Mac/Linux）
#
# 用法:
#   bash install.sh [项目目录]
#   bash install.sh --url http://<服务器IP>:3927 [项目目录]

set -e

SERVER_URL=""
TARGET_DIR="."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 解析参数
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) SERVER_URL="$2"; shift 2 ;;
    *) TARGET_DIR="$1"; shift ;;
  esac
done

TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

# 获取规则内容
get_rules() {
  if [[ -n "$SERVER_URL" ]]; then
    curl -sf "${SERVER_URL}/rules/rule-porter.md" || { echo "错误: 无法从 ${SERVER_URL}/rules/rule-porter.md 获取规则"; exit 1; }
  else
    local local_file="$SCRIPT_DIR/rule-porter.md"
    [[ -f "$local_file" ]] || { echo "错误: 找不到 $local_file"; exit 1; }
    cat "$local_file"
  fi
}

RULES_CONTENT="$(get_rules)"

# 写入规则文件
install_rule() {
  local file="$1"
  local dir="$(dirname "$file")"
  [[ -d "$dir" ]] || mkdir -p "$dir"

  if [[ -f "$file" ]]; then
    # 已有内容则追加
    if ! grep -q "rule-porter-mcp" "$file" 2>/dev/null; then
      printf "\n\n%s" "$RULES_CONTENT" >> "$file"
      echo "  追加到 $file"
    else
      echo "  跳过 $file（已包含规则）"
    fi
  else
    echo "$RULES_CONTENT" > "$file"
    echo "  创建 $file"
  fi
}

echo "扫描项目: $TARGET_DIR"
echo ""

INSTALLED=0

# Claude Code
if [[ -f "$TARGET_DIR/CLAUDE.md" ]] || [[ -d "$TARGET_DIR/.claude" ]] || [[ -f "$TARGET_DIR/.claude.json" ]]; then
  install_rule "$TARGET_DIR/CLAUDE.md"
  INSTALLED=1
fi

# Cursor
if [[ -f "$TARGET_DIR/.cursorrules" ]] || [[ -d "$TARGET_DIR/.cursor" ]]; then
  install_rule "$TARGET_DIR/.cursorrules"
  INSTALLED=1
fi

# Windsurf
if [[ -f "$TARGET_DIR/.windsurfrules" ]] || [[ -d "$TARGET_DIR/.windsurf" ]]; then
  install_rule "$TARGET_DIR/.windsurfrules"
  INSTALLED=1
fi

# GitHub Copilot
if [[ -d "$TARGET_DIR/.github" ]]; then
  install_rule "$TARGET_DIR/.github/copilot-instructions.md"
  INSTALLED=1
fi

# Cline
if [[ -f "$TARGET_DIR/.clinerules" ]] || [[ -d "$TARGET_DIR/.cline" ]]; then
  install_rule "$TARGET_DIR/.clinerules"
  INSTALLED=1
fi

# Kiro
if [[ -d "$TARGET_DIR/.kiro" ]]; then
  install_rule "$TARGET_DIR/.kiro/steering/rule-porter.md"
  INSTALLED=1
fi

# 未检测到任何 AI 工具，默认写入 CLAUDE.md
if [[ $INSTALLED -eq 0 ]]; then
  echo "  未检测到已知 AI 工具，默认写入 CLAUDE.md"
  install_rule "$TARGET_DIR/CLAUDE.md"
fi

echo ""
echo "安装完成"

# 生成 .rule-porter/config.json
CONFIG_DIR="$TARGET_DIR/.rule-porter"
CONFIG_FILE="$CONFIG_DIR/config.json"
if [[ -f "$CONFIG_FILE" ]]; then
  echo "  跳过 $CONFIG_FILE（已存在）"
else
  PROJECT_NAME="$(basename "$TARGET_DIR")"
  mkdir -p "$CONFIG_DIR"
  cat > "$CONFIG_FILE" <<EOF
{
  "project": "$PROJECT_NAME"
}
EOF
  echo "  创建 $CONFIG_FILE (project: $PROJECT_NAME)"
fi
