#!/usr/bin/env bash
# 把本仓库安装为 OpenHarness 的用户级插件。
#
# 用法：
#   ./scripts/install.sh                  # 复制到 ${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard
#   ./scripts/install.sh --link           # 软链接（开发用，修改立即生效）
#   ./scripts/install.sh --force          # 覆盖已有安装
#   ./scripts/install.sh /custom/plugins  # 安装到自定义插件根目录下的 guard/
set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  ./scripts/install.sh                  # 复制到 ${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard
  ./scripts/install.sh --link           # 软链接（开发用，修改立即生效）
  ./scripts/install.sh --force          # 覆盖已有安装
  ./scripts/install.sh /custom/plugins  # 安装到自定义插件根目录下的 guard/
EOF
}

FORCE=0
LINK=0
POSITIONAL=()

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --link) LINK=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      POSITIONAL+=("$arg")
      ;;
  esac
done

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="${POSITIONAL[0]:-${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins}"
DEST="$DEST_ROOT/guard"

if [ ! -f "$SRC/plugin.json" ]; then
  echo "未找到 $SRC/plugin.json，请在 guard 仓库中运行该脚本。" >&2
  exit 1
fi

if [ -e "$DEST" ] || [ -L "$DEST" ]; then
  if [ "$FORCE" -ne 1 ]; then
    echo "guard 已存在于 $DEST" >&2
    echo "如需覆盖，请运行：$0 --force（软链接请用 --force --link）" >&2
    exit 1
  fi
  rm -rf "$DEST"
fi

mkdir -p "$DEST_ROOT"

if [ "$LINK" -eq 1 ]; then
  if [ "$(uname -s)" = "Windows_NT" ] || [[ "${OS:-}" == Windows_NT ]]; then
    echo "Windows 下软链接可能需要开发者模式或管理员权限；失败时请改用复制安装。" >&2
  fi
  ln -s "$SRC" "$DEST"
  echo "已创建软链接：$DEST -> $SRC"
else
  mkdir -p "$DEST"
  tar -C "$SRC" \
    --exclude=.git \
    --exclude=.venv \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude=.pytest_cache \
    -cf - . | tar -C "$DEST" -xf -
  chmod +x "$DEST/hooks/guard_hook.py" "$DEST/hooks/guard_audit.py" \
    "$DEST/scripts/guard-config.py" 2>/dev/null || true
  echo "已复制 guard 到 $DEST"
fi

echo
echo "下一步："
if [ "$LINK" -eq 0 ] && [ "$DEST" != "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard" ]; then
  echo "  * 非默认位置，请设置：export OPENHARNESS_GUARD_ROOT=\"$DEST\""
fi
echo "  * 启动 oh，运行 /plugin 或 /reload-plugins 确认 guard 已加载"
echo "  * 可选：配置邮箱通知（~/.openharness/guard-email.json，见 examples/）"
