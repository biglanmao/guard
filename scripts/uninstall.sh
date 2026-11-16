#!/usr/bin/env bash
# 从插件根目录移除本仓库安装的插件。
#
# 只删除「plugin.json 的 name 与目录名一致」的目标；符号链接只删链接本身，
# 不动仓库。用户配置（~/.openharness/guard-email.json）与审计日志不会被删除。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
. "$HERE/common.sh"

usage() {
  cat <<'EOF'
用法：
  ./scripts/uninstall.sh                # 从用户插件根移除本仓库的全部插件
  ./scripts/uninstall.sh --list         # 列出插件及其安装状态，不删除
  ./scripts/uninstall.sh --only guard   # 只移除指定插件；可逗号分隔或重复 --only
  ./scripts/uninstall.sh --all          # 显式移除全部（默认；会重置 --only）
  ./scripts/uninstall.sh --dry-run      # 只打印将要移除的内容
  ./scripts/uninstall.sh /custom/plugins  # 操作自定义插件根目录

默认目标：${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins
EOF
}

DRY_RUN=0
LIST_ONLY=0
SELECT=""
POSITIONAL=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --all) SELECT=""; shift ;;
    --only)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "--only 需要一个插件名，例如 --only guard" >&2
        exit 1
      fi
      if [ -z "$SELECT" ]; then SELECT="$2"; else SELECT="$SELECT,$2"; fi
      shift 2
      ;;
    --only=*)
      if [ -z "$SELECT" ]; then SELECT="${1#--only=}"; else SELECT="$SELECT,${1#--only=}"; fi
      shift
      ;;
    --list) LIST_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "未知参数：$1" >&2; usage >&2; exit 1 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

SRC="$(cd "$HERE/.." && pwd)"
discover_plugins "$SRC/plugins"
DEST_ROOT="${POSITIONAL[0]:-$(default_plugins_root)}"

case "$DEST_ROOT" in
  ""|"/"|"$HOME"|"$HOME/") die "拒绝在 $DEST_ROOT 上执行移除，请指定插件根目录。" ;;
esac

# 描述某个插件的安装状态：未安装 / 软链接 / 复制
install_state() {
  local target="$1" name="$2"
  if [ -L "$target" ]; then
    echo "软链接"
  elif [ -e "$target" ]; then
    if is_our_plugin "$target" "$name"; then
      echo "复制 $(plugin_manifest_field "$target/plugin.json" version)"
    else
      echo "被占用（不是本仓库的插件）"
    fi
  else
    echo "未安装"
  fi
}

if [ "$LIST_ONLY" -eq 1 ]; then
  echo "插件状态（$DEST_ROOT）："
  for i in "${!PLUGIN_NAMES[@]}"; do
    name="${PLUGIN_NAMES[$i]}"
    printf '  %-12s %s\n' "$name" "$(install_state "$DEST_ROOT/$name" "$name")"
  done
  exit 0
fi

select_plugins "$SELECT"

if [ ! -d "$DEST_ROOT" ]; then
  echo "$DEST_ROOT 不存在，没有可移除的插件。"
  exit 0
fi

REMOVED=()
SKIPPED=()

for name in "${PLUGIN_NAMES[@]}"; do
  target="$DEST_ROOT/$name"
  if [ -L "$target" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "将移除软链接：$target -> $(readlink "$target")"
    else
      rm -f "$target"
      echo "已移除软链接：$target"
    fi
    REMOVED+=("$name")
  elif [ -e "$target" ]; then
    if is_our_plugin "$target" "$name"; then
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "将删除目录：$target"
      else
        rm -rf "$target"
        echo "已删除目录：$target"
      fi
      REMOVED+=("$name")
    else
      echo "跳过 $target：plugin.json 的 name 不是 $name，可能不是本仓库的插件。" >&2
      SKIPPED+=("$name")
    fi
  else
    SKIPPED+=("$name")
  fi
done

echo
if [ "${#REMOVED[@]}" -eq 0 ]; then
  echo "没有移除任何插件（$DEST_ROOT）。"
else
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "演练模式：未实际删除。将移除：${REMOVED[*]}"
  else
    echo "已移除：${REMOVED[*]}"
  fi
fi
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  echo "未处理：${SKIPPED[*]}（未安装或不属于本仓库）"
fi

case " ${REMOVED[*]} " in
  *" guard "*)
    echo "提示：guard 的 hook 已不再加载；若曾设置 OPENHARNESS_GUARD_ROOT，可一并清理。"
    ;;
esac
echo "提示：配置（${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/guard-email.json）与审计日志不会被删除，需要时手动清理。"
