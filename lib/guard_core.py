"""guard 策略引擎：在工具调用前判断是否命中高风险规则。

只依赖 Python 标准库，便于被 hook 脚本、插件工具和测试直接导入。

策略文件的查找顺序：

1. 显式传入的 ``path``
2. 环境变量 ``OPENHARNESS_GUARD_POLICY``
3. 插件内置的 ``policies/default.json``
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_PATH = PLUGIN_ROOT / "policies" / "default.json"

VALID_MODES = ("off", "audit", "enforce")
DEFAULT_MODE = "enforce"

_COMPILED: dict[str, re.Pattern[str]] = {}


class PolicyError(RuntimeError):
    """策略文件缺失或格式错误。"""


@dataclass(frozen=True)
class Decision:
    """一次策略判定的结果。"""

    allowed: bool
    action: str
    tool_name: str
    rule_id: str | None = None
    reason: str = ""
    matched: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "allowed": self.allowed,
            "action": self.action,
            "tool_name": self.tool_name,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "matched": self.matched,
        }


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate a policy file."""
    configured = path or os.environ.get("OPENHARNESS_GUARD_POLICY") or DEFAULT_POLICY_PATH
    policy_path = Path(configured).expanduser()
    try:
        raw = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError(f"无法读取策略文件 {policy_path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyError(f"策略文件 {policy_path} 不是合法 JSON: {exc}") from exc
    _validate_policy(data, policy_path)
    return data


def _validate_policy(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise PolicyError(f"策略文件 {path} 顶层必须是对象")
    mode = data.get("mode", DEFAULT_MODE)
    if mode not in VALID_MODES:
        raise PolicyError(f"策略文件 {path} 的 mode 必须是 {VALID_MODES} 之一")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise PolicyError(f"策略文件 {path} 必须包含 rules 数组")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise PolicyError(f"第 {index} 条规则必须是对象")
        for key in ("id", "regex"):
            if not isinstance(rule.get(key), str) or not rule[key].strip():
                raise PolicyError(f"第 {index} 条规则缺少字符串字段 {key}")
        action = rule.get("action", "deny")
        if action not in ("deny", "warn"):
            raise PolicyError(f"规则 {rule['id']} 的 action 必须是 deny 或 warn")
        try:
            re.compile(rule["regex"])
        except re.error as exc:
            raise PolicyError(f"规则 {rule['id']} 的正则无效: {exc}") from exc


def resolve_mode(policy: Mapping[str, Any] | None = None, mode: str | None = None) -> str:
    """Resolve the active mode: argument > environment > policy > default."""
    candidate = (mode or os.environ.get("OPENHARNESS_GUARD_MODE") or (policy or {}).get("mode") or DEFAULT_MODE)
    candidate = str(candidate).lower()
    return candidate if candidate in VALID_MODES else DEFAULT_MODE


def _compiled(pattern: str) -> re.Pattern[str]:
    regex = _COMPILED.get(pattern)
    if regex is None:
        regex = re.compile(pattern)
        _COMPILED[pattern] = regex
    return regex


def _iter_strings(value: Any) -> Iterator[str]:
    """Yield every string leaf inside an arbitrarily nested value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, bool):
        yield "true" if value else "false"
    elif value is not None:
        yield str(value)


def _candidate_texts(rule: Mapping[str, Any], tool_input: Mapping[str, Any]) -> Iterator[str]:
    fields = rule.get("fields")
    if isinstance(fields, list) and fields:
        for field in fields:
            if field in tool_input:
                values = [tool_input[field]]
            else:
                values = []
            for value in values:
                for text in _iter_strings(value):
                    yield text
    else:
        for text in _iter_strings(tool_input):
            yield text


def _tool_matches(rule: Mapping[str, Any], tool_name: str) -> bool:
    patterns = rule.get("tools") or ["*"]
    if not isinstance(patterns, list):
        patterns = [patterns]
    lowered = tool_name.lower()
    return any(fnmatch.fnmatchcase(lowered, str(pattern).lower()) for pattern in patterns)


def check(
    tool_name: str,
    tool_input: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    *,
    mode: str | None = None,
) -> Decision:
    """Evaluate ``tool_name``/``tool_input`` against the policy.

    ``off`` disables evaluation, ``audit`` reports matches without blocking,
    and ``enforce`` blocks rules whose action is ``deny``.
    """
    policy = policy if policy is not None else load_policy()
    active_mode = resolve_mode(policy, mode)
    tool_name = str(tool_name or "")
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}

    if active_mode == "off" or not tool_name:
        return Decision(allowed=True, action="allow", tool_name=tool_name)

    for rule in policy.get("rules", []):
        if not isinstance(rule, Mapping) or not _tool_matches(rule, tool_name):
            continue
        regex = _compiled(str(rule["regex"]))
        for text in _candidate_texts(rule, tool_input):
            variants = {text}
            if "\\" in text:
                variants.add(text.replace("\\", "/"))
            for variant in variants:
                match = regex.search(variant)
                if match is None:
                    continue
                rule_id = str(rule["id"])
                reason = str(rule.get("reason") or rule.get("description") or "命中安全规则")
                matched = match.group(0)[:200]
                if rule.get("action", "deny") == "warn":
                    return Decision(True, "warn", tool_name, rule_id, reason, matched)
                if active_mode == "audit":
                    return Decision(True, "audit", tool_name, rule_id, reason, matched)
                return Decision(False, "deny", tool_name, rule_id, reason, matched)

    return Decision(allowed=True, action="allow", tool_name=tool_name)
