#!/usr/bin/env bash
# 把本仓库 plugins/ 下的插件安装到插件根目录。
#
# 仓库按插件拆分：每个插件自成一包（plugins/<名称>），可以整包装，也可以只挑其中几个装。
set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  ./scripts/install.sh                  # 复制安装 plugins/ 下的全部插件
  ./scripts/install.sh --list           # 列出仓库里的插件，不安装
  ./scripts/install.sh --only guard     # 只安装指定插件；可逗号分隔或重复 --only
  ./scripts/install.sh --all            # 显式安装全部（默认；会重置 --only）
  ./scripts/install.sh --link           # 软链接（开发用，修改立即生效）
  ./scripts/install.sh --force          # 覆盖已有安装
  ./scripts/install.sh /custom/plugins  # 安装到自定义插件根目录

默认目标：${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/<插件名>
EOF
}

FORCE=0
LINK=0
LIST_ONLY=0
SELECT=""
POSITIONAL=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --link) LINK=1; shift ;;
    --all) SELECT=""; shift ;;
    --only)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "--only 需要一个插件名，例如 --only guard 或 --only guard,ask_image" >&2
        exit 1
      fi
      # 允许多次 --only，累加成逗号分隔的列表。
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

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_PLUGINS="$SRC/plugins"
DEST_ROOT="${POSITIONAL[0]:-${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins}"

if [ ! -d "$SRC_PLUGINS" ]; then
  echo "未找到 $SRC_PLUGINS，请在插件集合仓库中运行该脚本。" >&2
  exit 1
fi

# 发现插件并校验清单：目录名必须与 plugin.json 的 name 一致。
PLUGIN_DIRS=()
PLUGIN_NAMES=()
PLUGIN_VERSIONS=()
PLUGIN_DESCRIPTIONS=()
for dir in "$SRC_PLUGINS"/*/; do
  dir="${dir%/}"
  [ -f "$dir/plugin.json" ] || continue
  meta="$(python3 - "$dir/plugin.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
print(manifest["name"])
print(manifest.get("version", "0.0.0"))
print(" ".join(manifest.get("description", "").split()))
PY
)"
  name="$(printf '%s\n' "$meta" | sed -n '1p')"
  version="$(printf '%s\n' "$meta" | sed -n '2p')"
  description="$(printf '%s\n' "$meta" | sed -n '3p')"
  if [ "$name" != "$(basename "$dir")" ]; then
    echo "$dir/plugin.json 的 name=$name 与目录名不一致，请修正后再安装。" >&2
    exit 1
  fi
  PLUGIN_DIRS+=("$dir")
  PLUGIN_NAMES+=("$name")
  PLUGIN_VERSIONS+=("$version")
  PLUGIN_DESCRIPTIONS+=("$description")
done

if [ "${#PLUGIN_DIRS[@]}" -eq 0 ]; then
  echo "$SRC_PLUGINS 下没有找到任何 plugin.json。" >&2
  exit 1
fi

if [ "$LIST_ONLY" -eq 1 ]; then
  echo "可安装插件（$SRC_PLUGINS）："
  for i in "${!PLUGIN_NAMES[@]}"; do
    printf '  %-12s %-8s %s\n' "${PLUGIN_NAMES[$i]}" "${PLUGIN_VERSIONS[$i]}" "${PLUGIN_DESCRIPTIONS[$i]}"
  done
  exit 0
fi

# --only 过滤：按名称挑插件，未知名直接报错，避免"以为装了其实没装"。
if [ -n "$SELECT" ]; then
  SELECTED_DIRS=()
  SELECTED_NAMES=()
  IFS=',' read -r -a WANTED <<< "$SELECT"
  for wanted in "${WANTED[@]}"; do
    wanted="$(printf '%s' "$wanted" | tr -d '[:space:]')"
    [ -n "$wanted" ] || continue
    found=0
    for i in "${!PLUGIN_NAMES[@]}"; do
      if [ "${PLUGIN_NAMES[$i]}" = "$wanted" ]; then
        SELECTED_DIRS+=("${PLUGIN_DIRS[$i]}")
        SELECTED_NAMES+=("${PLUGIN_NAMES[$i]}")
        found=1
        break
      fi
    done
    if [ "$found" -eq 0 ]; then
      echo "未找到插件：$wanted（可用：${PLUGIN_NAMES[*]}）" >&2
      exit 1
    fi
  done
  if [ "${#SELECTED_NAMES[@]}" -eq 0 ]; then
    echo "--only 没有解析出任何插件名：$SELECT" >&2
    exit 1
  fi
  PLUGIN_DIRS=("${SELECTED_DIRS[@]}")
  PLUGIN_NAMES=("${SELECTED_NAMES[@]}")
fi

# 先整体检查冲突，避免装到一半失败。
CONFLICTS=()
for name in "${PLUGIN_NAMES[@]}"; do
  dest="$DEST_ROOT/$name"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    CONFLICTS+=("$name")
  fi
done
if [ "${#CONFLICTS[@]}" -gt 0 ] && [ "$FORCE" -ne 1 ]; then
  echo "以下插件已存在于 $DEST_ROOT：${CONFLICTS[*]}" >&2
  echo "如需覆盖，请运行：$0 --force（软链接请用 --force --link）" >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"

if [ "$LINK" -eq 1 ] && { [ "$(uname -s)" = "Windows_NT" ] || [[ "${OS:-}" == Windows_NT ]]; }; then
  echo "Windows 下软链接可能需要开发者模式或管理员权限；失败时请改用复制安装。" >&2
fi

for i in "${!PLUGIN_DIRS[@]}"; do
  dir="${PLUGIN_DIRS[$i]}"
  name="${PLUGIN_NAMES[$i]}"
  dest="$DEST_ROOT/$name"

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    rm -rf "$dest"
  fi

  if [ "$LINK" -eq 1 ]; then
    ln -s "$dir" "$dest"
    echo "已创建软链接：$dest -> $dir"
  else
    mkdir -p "$dest"
    tar -C "$dir" \
      --exclude=.git \
      --exclude=.venv \
      --exclude=__pycache__ \
      --exclude='*.pyc' \
      --exclude=.pytest_cache \
      -cf - . | tar -C "$dest" -xf -
    # 安装后的脚本需要可执行位；tar 已保留权限，这里兜底。
    find "$dest" -type f \( -name '*.py' -o -name '*.sh' \) \
      -path '*/scripts/*' -exec chmod +x {} + 2>/dev/null || true
    find "$dest/hooks" -type f -name '*.py' -exec chmod +x {} + 2>/dev/null || true
    echo "已复制 $name 到 $dest"
  fi
done

echo
echo "已安装插件：${PLUGIN_NAMES[*]}（$DEST_ROOT）"
echo "未安装的插件不会加载；需要更多插件时重跑本脚本并加 --only <名称>。"
echo "下一步："
DEFAULT_USER_ROOT="${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins"
OHMO_ROOT="${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins"
if [ "$LINK" -eq 0 ] && [ "$DEST_ROOT" != "$DEFAULT_USER_ROOT" ] && [ "$DEST_ROOT" != "$OHMO_ROOT" ]; then
  case " ${PLUGIN_NAMES[*]} " in
    *" guard "*)
      echo "  * 非默认位置，guard 的 hook 需要显式指路：export OPENHARNESS_GUARD_ROOT=\"$DEST_ROOT/guard\""
      ;;
    *)
      echo "  * 非默认位置：如需 guard 的 hook 生效，请 export OPENHARNESS_GUARD_ROOT=\"$DEST_ROOT/guard\""
      ;;
  esac
fi
if [ "$DEST_ROOT" = "$OHMO_ROOT" ]; then
  echo "  * 已安装到 ohmo 工作区，启动 ohmo 即可加载（运行 /plugin 查看）"
else
  echo "  * 启动 oh，运行 /plugin 或 /reload-plugins 确认已加载"
fi
case " ${PLUGIN_NAMES[*]} " in
  *" guard-email "*)
    echo "  * 可选：配置邮箱通知（~/.openharness/guard-email.json，见 guard-email 插件 examples/）"
    case " ${PLUGIN_NAMES[*]} " in
      *" guard "*)
        ;;
      *)
        echo "  * 注意：没装 guard，邮件外发不会被拦截（敏感附件检查由 guard 提供）；"
        echo "    需要时再运行：$0 --only guard"
        ;;
    esac
    ;;
esac
