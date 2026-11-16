#!/usr/bin/env bash
# 把已安装的本仓库插件重装成当前 checkout 的内容（即「更新」）。
#
# 只处理已经装在目标根目录里的插件：复制安装的插件会被覆盖重装，软链接安装的
# 插件本来就指向仓库、无需更新。不会顺带安装未安装的插件。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
. "$HERE/common.sh"

usage() {
  cat <<'EOF'
用法：
  ./scripts/update.sh                   # 重装已安装的本仓库插件
  ./scripts/update.sh --only guard      # 只更新指定插件；可逗号分隔或重复 --only
  ./scripts/update.sh --dry-run         # 只打印将要更新什么
  ./scripts/update.sh /custom/plugins   # 操作自定义插件根目录

不会安装尚未安装的插件；那一步请用 ./scripts/install.sh --only <名称>。
软链接安装的插件指向仓库，无需更新。
EOF
}

DRY_RUN=0
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
    -h|--help) usage; exit 0 ;;
    -*) echo "未知参数：$1" >&2; usage >&2; exit 1 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

SRC="$(cd "$HERE/.." && pwd)"
discover_plugins "$SRC/plugins"
DEST_ROOT="${POSITIONAL[0]:-$(default_plugins_root)}"
select_plugins "$SELECT"

TO_UPDATE=()
LINKED=()
MISSING=()
FOREIGN=()

for i in "${!PLUGIN_NAMES[@]}"; do
  name="${PLUGIN_NAMES[$i]}"
  target="$DEST_ROOT/$name"
  if [ -L "$target" ]; then
    LINKED+=("$name")
  elif [ -e "$target" ]; then
    if is_our_plugin "$target" "$name"; then
      installed_version="$(plugin_manifest_field "$target/plugin.json" version)"
      TO_UPDATE+=("$name")
      echo "更新 $name：$installed_version -> ${PLUGIN_VERSIONS[$i]}"
    else
      FOREIGN+=("$name")
    fi
  else
    MISSING+=("$name")
  fi
done

if [ "${#LINKED[@]}" -gt 0 ]; then
  for name in "${LINKED[@]}"; do
    echo "跳过 $name：软链接安装，指向仓库，修改即时生效。"
  done
fi
if [ "${#FOREIGN[@]}" -gt 0 ]; then
  for name in "${FOREIGN[@]}"; do
    echo "跳过 $DEST_ROOT/$name：plugin.json 的 name 不是 $name，可能不是本仓库的插件。" >&2
  done
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  for name in "${MISSING[@]}"; do
    echo "跳过 $name：未安装（需要时装一次：./scripts/install.sh --only $name）"
  done
fi

if [ "${#TO_UPDATE[@]}" -eq 0 ]; then
  echo
  echo "没有需要更新的插件（$DEST_ROOT）。"
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "演练模式：未实际改动。将重装：${TO_UPDATE[*]}"
  exit 0
fi

echo
JOINED="$(IFS=,; echo "${TO_UPDATE[*]}")"
exec "$SRC/scripts/install.sh" --force --only "$JOINED" "$DEST_ROOT"
