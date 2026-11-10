#!/usr/bin/env python3
"""OpenHarness pre_tool_use hook：命中策略时以非零退出码阻止工具执行。

OpenHarness 会把事件数据放进 ``OPENHARNESS_HOOK_PAYLOAD`` 环境变量，并把
hook 的非零退出码视为拦截（hooks.json 中 ``block_on_failure: true``）。

设计取舍：引擎自身出错时 **fail-open**（退出 0），避免因为策略文件损坏而
让整个 Agent 无法使用工具；错误信息会写到 stderr。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))


def _read_payload() -> dict:
    raw = os.environ.get("OPENHARNESS_HOOK_PAYLOAD", "").strip()
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def main() -> int:
    try:
        from guard_core import check, load_policy

        payload = _read_payload()
        tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
        tool_input = payload.get("tool_input") or payload.get("arguments") or {}
        if not isinstance(tool_input, dict):
            tool_input = {"value": tool_input}

        decision = check(tool_name, tool_input, load_policy())
    except Exception as exc:  # noqa: BLE001 - fail-open by design
        print(f"[guard] 策略引擎异常，已放行：{exc}", file=sys.stderr)
        return 0

    if decision.allowed:
        if decision.action in ("audit", "warn"):
            label = "audit" if decision.action == "audit" else "warn"
            print(
                f"[guard][{label}] {tool_name} 命中规则 {decision.rule_id}：{decision.reason}",
                file=sys.stderr,
            )
        return 0

    print(
        f"[guard] 已拦截工具 {tool_name}（规则 {decision.rule_id}）：{decision.reason}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
