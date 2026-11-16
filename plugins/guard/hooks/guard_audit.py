#!/usr/bin/env python3
"""OpenHarness post_tool_use hook：把工具调用追加到审计日志（JSONL）。

默认写入 ``$OPENHARNESS_LOGS_DIR/guard-audit.jsonl``，未设置时写入
``~/.openharness/logs/guard-audit.jsonl``。可用 ``OPENHARNESS_GUARD_AUDIT_LOG``
覆盖具体文件路径。审计失败不会阻断 Agent（``block_on_failure: false``）。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

MAX_FIELD_CHARS = 4000


def _log_path() -> Path:
    explicit = os.environ.get("OPENHARNESS_GUARD_AUDIT_LOG")
    if explicit:
        return Path(explicit).expanduser()
    logs_dir = os.environ.get("OPENHARNESS_LOGS_DIR")
    base = Path(logs_dir).expanduser() if logs_dir else Path.home() / ".openharness" / "logs"
    return base / "guard-audit.jsonl"


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
        payload = _read_payload()
        entry = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "event": payload.get("event", "post_tool_use"),
            "tool_name": payload.get("tool_name") or payload.get("tool"),
            "tool_input": payload.get("tool_input") or payload.get("arguments"),
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        if len(line) > MAX_FIELD_CHARS:
            line = line[:MAX_FIELD_CHARS] + "…(truncated)"
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as exc:  # noqa: BLE001 - audit must never block
        print(f"[guard] 审计日志写入失败：{exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
