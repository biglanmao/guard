#!/usr/bin/env bash
# install.sh / uninstall.sh / update.sh 共用的插件发现与路径工具。
# 调用方需先设置 SRC（仓库根）并启用 set -euo pipefail。

die() {
  echo "$*" >&2
  exit 1
}

# 读取 plugin.json 的某个字段；description 会压成一行。
plugin_manifest_field() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
value = manifest.get(sys.argv[2], "")
if isinstance(value, str):
    print(" ".join(value.split()))
else:
    print(value)
PY
}

# 发现 <仓库>/plugins/* 并校验「目录名 == manifest.name」。
# 结果写入 PLUGIN_DIRS / PLUGIN_NAMES / PLUGIN_VERSIONS / PLUGIN_DESCRIPTIONS。
discover_plugins() {
  local src_plugins="$1" dir name version description
  PLUGIN_DIRS=()
  PLUGIN_NAMES=()
  PLUGIN_VERSIONS=()
  PLUGIN_DESCRIPTIONS=()
  [ -d "$src_plugins" ] || die "未找到 $src_plugins，请在插件集合仓库中运行该脚本。"
  for dir in "$src_plugins"/*/; do
    dir="${dir%/}"
    [ -f "$dir/plugin.json" ] || continue
    name="$(plugin_manifest_field "$dir/plugin.json" name)"
    version="$(plugin_manifest_field "$dir/plugin.json" version)"
    description="$(plugin_manifest_field "$dir/plugin.json" description)"
    if [ "$name" != "$(basename "$dir")" ]; then
      die "$dir/plugin.json 的 name=$name 与目录名不一致，请修正后再试。"
    fi
    PLUGIN_DIRS+=("$dir")
    PLUGIN_NAMES+=("$name")
    PLUGIN_VERSIONS+=("$version")
    PLUGIN_DESCRIPTIONS+=("$description")
  done
  [ "${#PLUGIN_DIRS[@]}" -gt 0 ] || die "$src_plugins 下没有找到任何 plugin.json。"
}

# 按逗号分隔的名称过滤 PLUGIN_* 数组；未知名直接失败，避免「以为处理了其实没处理」。
select_plugins() {
  local select="$1" wanted found i
  local selected_dirs=() selected_names=() selected_versions=() selected_descriptions=()
  [ -n "$select" ] || return 0
  IFS=',' read -r -a WANTED <<< "$select"
  for wanted in "${WANTED[@]}"; do
    wanted="$(printf '%s' "$wanted" | tr -d '[:space:]')"
    [ -n "$wanted" ] || continue
    found=0
    for i in "${!PLUGIN_NAMES[@]}"; do
      if [ "${PLUGIN_NAMES[$i]}" = "$wanted" ]; then
        selected_dirs+=("${PLUGIN_DIRS[$i]}")
        selected_names+=("${PLUGIN_NAMES[$i]}")
        selected_versions+=("${PLUGIN_VERSIONS[$i]}")
        selected_descriptions+=("${PLUGIN_DESCRIPTIONS[$i]}")
        found=1
        break
      fi
    done
    [ "$found" -eq 1 ] || die "未找到插件：$wanted（可用：${PLUGIN_NAMES[*]}）"
  done
  [ "${#selected_names[@]}" -gt 0 ] || die "--only 没有解析出任何插件名：$select"
  PLUGIN_DIRS=("${selected_dirs[@]}")
  PLUGIN_NAMES=("${selected_names[@]}")
  PLUGIN_VERSIONS=("${selected_versions[@]}")
  PLUGIN_DESCRIPTIONS=("${selected_descriptions[@]}")
}

default_plugins_root() {
  echo "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins"
}

ohmo_plugins_root() {
  echo "${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins"
}

# 判断目录是否是本仓库的插件（plugin.json 的 name 与目录名一致）。
is_our_plugin() {
  local dir="$1" expected="$2" actual
  [ -f "$dir/plugin.json" ] || return 1
  actual="$(plugin_manifest_field "$dir/plugin.json" name 2>/dev/null || true)"
  [ "$actual" = "$expected" ]
}
