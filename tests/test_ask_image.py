"""ask_image 插件的行为测试。

依赖 openharness 包与 pydantic：未安装时整类跳过，保证仓库测试在最小 Python
环境里也能跑（guard 插件自身不依赖第三方库）。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "ask_image"
TOOL_FILE = PLUGIN / "tools" / "ask_image.py"

try:  # pragma: no cover - 取决于运行环境
    from openharness.plugins.loader import _load_plugin_tools
    from openharness.plugins.schemas import PluginManifest
    from openharness.tools import image_to_text_tool
    from openharness.tools.base import ToolResult

    HAVE_OPENHARNESS = True
except Exception:  # noqa: BLE001 - 缺少依赖时跳过，不隐藏真实失败面
    HAVE_OPENHARNESS = False


def load_tool_module():
    spec = importlib.util.spec_from_file_location("ask_image_plugin_tool", TOOL_FILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAVE_OPENHARNESS, "需要安装 openharness 才能测试插件工具")
class AskImageToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_tool_module()
        self.tool = self.module.AskImageTool()

    def test_tool_identity(self) -> None:
        self.assertEqual(self.tool.name, "ask_image")
        self.assertTrue(self.tool.description)
        self.assertTrue(self.tool.is_read_only(None))

    def test_input_schema_requires_question(self) -> None:
        schema = self.tool.to_api_schema()["input_schema"]
        self.assertEqual(schema["required"], ["question"])
        for field in ("image_data", "image_path", "media_type", "max_tokens", "context"):
            self.assertIn(field, schema["properties"])

    def test_prompt_composition(self) -> None:
        arguments = self.module.AskImageInput(
            question="  报错框里写了什么？  ",
            context="CI 截图",
            image_path="shot.png",
        )
        prompt = self.module._compose_question_prompt(arguments)
        self.assertIn("Question: 报错框里写了什么？", prompt)
        self.assertIn("Additional context: CI 截图", prompt)
        self.assertNotIn("  \n", prompt)

    def test_prompt_composition_without_context(self) -> None:
        arguments = self.module.AskImageInput(question="有哪些按钮？")
        prompt = self.module._compose_question_prompt(arguments)
        self.assertIn("Question: 有哪些按钮？", prompt)
        self.assertNotIn("Additional context", prompt)

    def test_execute_delegates_with_question_prompt(self) -> None:
        captured: dict[str, object] = {}

        async def fake_execute(self, arguments, context):  # noqa: ANN001
            captured["prompt"] = arguments.prompt
            captured["image_path"] = arguments.image_path
            return ToolResult(output="[Image description via vision-x]\n\n按钮文案是 OK")

        original = image_to_text_tool.ImageToTextTool.execute
        image_to_text_tool.ImageToTextTool.execute = fake_execute
        try:
            result = asyncio.run(
                self.tool.execute(
                    self.module.AskImageInput(question="按钮文案是什么？", image_path="a.png"),
                    None,
                )
            )
        finally:
            image_to_text_tool.ImageToTextTool.execute = original

        self.assertIn("按钮文案是什么？", str(captured["prompt"]))
        self.assertEqual(captured["image_path"], "a.png")
        self.assertFalse(result.is_error)
        # 输出首行改称答案，避免用户看到 image_to_text 的字样。
        self.assertTrue(result.output.startswith("[Image answer via vision-x]"), result.output)

    def test_execute_relabels_error_prefix(self) -> None:
        async def failing_execute(self, arguments, context):  # noqa: ANN001
            return ToolResult(output="image_to_text failed: vision model is not configured.", is_error=True)

        original = image_to_text_tool.ImageToTextTool.execute
        image_to_text_tool.ImageToTextTool.execute = failing_execute
        try:
            result = asyncio.run(
                self.tool.execute(self.module.AskImageInput(question="报错内容？"), None)
            )
        finally:
            image_to_text_tool.ImageToTextTool.execute = original

        self.assertTrue(result.is_error)
        self.assertTrue(result.output.startswith("ask_image failed:"), result.output)


@unittest.skipUnless(HAVE_OPENHARNESS, "需要安装 openharness 才能测试插件加载")
class AskImagePluginTest(unittest.TestCase):
    def test_manifest_matches_directory(self) -> None:
        manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], PLUGIN.name)
        self.assertEqual(manifest.get("tools_dir", "tools"), "tools")

    def test_loader_registers_only_ask_image(self) -> None:
        manifest = PluginManifest.model_validate_json(
            (PLUGIN / "plugin.json").read_text(encoding="utf-8")
        )
        tools = _load_plugin_tools(PLUGIN, manifest)
        names = sorted(tool.name for tool in tools)
        # 只应注册 ask_image，不能把父类 image_to_text 也注册一遍。
        self.assertEqual(names, ["ask_image"])


if __name__ == "__main__":
    unittest.main()
