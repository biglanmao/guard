"""guard_check 工具：在真正执行前检查一次工具调用是否会命中护栏规则。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "lib"))


class GuardCheckInput(BaseModel):
    """guard_check 的参数。"""

    tool_name: str = Field(description="要检查的工具名，例如 bash、write_file、read_file")
    tool_input: dict[str, Any] = Field(
        default_factory=dict,
        description="该工具的参数对象，例如 {\"command\": \"rm -rf /\"}",
    )
    mode: str | None = Field(
        default=None,
        description="可选：off / audit / enforce，覆盖策略文件与环境变量中的模式",
    )


class GuardCheckTool(BaseTool):
    """预演一次工具调用，返回 guard 的判定结果。"""

    name = "guard_check"
    description = (
        "在真正执行前检查某个工具调用是否会触发 guard 安全规则。"
        "返回 allowed、命中的规则与原因，不会执行被检查的工具。"
    )
    input_model = GuardCheckInput

    def is_read_only(self, arguments: GuardCheckInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: GuardCheckInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        del context
        from guard_core import PolicyError, check, load_policy

        try:
            decision = check(
                arguments.tool_name,
                arguments.tool_input,
                load_policy(),
                mode=arguments.mode,
            )
        except PolicyError as exc:
            return ToolResult(output=f"策略加载失败：{exc}", is_error=True)

        return ToolResult(
            output=json.dumps(decision.to_dict(), ensure_ascii=False, indent=2),
            metadata={"allowed": decision.allowed, "rule_id": decision.rule_id},
        )
