"""插件布局与 hook 集成测试。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginLayoutTest(unittest.TestCase):
    def test_manifest(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "guard")
        self.assertTrue(manifest["version"])
        self.assertTrue(manifest["description"])
        for key in ("skills_dir", "tools_dir", "hooks_file", "mcp_file"):
            self.assertTrue((ROOT / manifest[key]).exists(), f"缺少 {manifest[key]}")

    def test_extension_points_exist(self) -> None:
        self.assertTrue((ROOT / "skills" / "guard-safety" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "commands" / "audit.md").is_file())
        self.assertTrue((ROOT / "commands" / "email.md").is_file())
        self.assertTrue((ROOT / "agents" / "guard-reviewer.md").is_file())
        self.assertTrue((ROOT / "tools" / "guard_check.py").is_file())
        self.assertTrue((ROOT / "tools" / "send_email.py").is_file())
        self.assertTrue((ROOT / "lib" / "mailer.py").is_file())
        self.assertTrue((ROOT / "hooks" / "guard_hook.py").is_file())
        self.assertTrue((ROOT / "hooks" / "guard_audit.py").is_file())
        self.assertTrue((ROOT / "policies" / "default.json").is_file())
        self.assertTrue((ROOT / "examples" / "guard-email.example.json").is_file())
        self.assertTrue((ROOT / "scripts" / "guard-config.py").is_file())

    def test_hooks_configuration(self) -> None:
        hooks = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
        pre = hooks["pre_tool_use"]
        self.assertEqual(pre[0]["type"], "command")
        self.assertTrue(pre[0]["block_on_failure"])
        self.assertIn("guard_hook.py", pre[0]["command"])
        self.assertIn("$PWD/.openharness/plugins/guard", pre[0]["command"])
        self.assertFalse(hooks["post_tool_use"][0]["block_on_failure"])

    def test_mcp_configuration(self) -> None:
        mcp = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
        self.assertIsInstance(mcp["mcpServers"], dict)


class HookIntegrationTest(unittest.TestCase):
    def run_hook(self, payload: dict, **env_overrides: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "OPENHARNESS_HOOK_PAYLOAD": json.dumps(payload),
            **env_overrides,
        }
        return subprocess.run(
            [sys.executable, str(ROOT / "hooks" / "guard_hook.py")],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )

    def test_dangerous_call_is_blocked(self) -> None:
        result = self.run_hook({"tool_name": "bash", "tool_input": {"command": "rm -rf /"}})
        self.assertEqual(result.returncode, 2)
        self.assertIn("destructive-rm-root", result.stderr)

    def test_benign_call_passes(self) -> None:
        result = self.run_hook({"tool_name": "bash", "tool_input": {"command": "ls -la"}})
        self.assertEqual(result.returncode, 0)

    def test_audit_mode_passes_with_warning(self) -> None:
        result = self.run_hook(
            {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}},
            OPENHARNESS_GUARD_MODE="audit",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("audit", result.stderr)

    def test_invalid_policy_fails_open(self) -> None:
        result = self.run_hook(
            {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}},
            OPENHARNESS_GUARD_POLICY="/nonexistent/policy.json",
        )
        self.assertEqual(result.returncode, 0)


class InstallResolutionTest(unittest.TestCase):
    """hooks.json 的命令必须能在三种安装位置中找到脚本。"""

    def hook_command(self) -> str:
        hooks = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
        return hooks["pre_tool_use"][0]["command"]

    def base_env(self, root: Path) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "OPENHARNESS_CONFIG_DIR",
                "OPENHARNESS_GUARD_ROOT",
                "OPENHARNESS_GUARD_POLICY",
                "OPENHARNESS_GUARD_MODE",
            }
        }
        env["HOME"] = str(root / "home")
        env["OPENHARNESS_HOOK_PAYLOAD"] = json.dumps(
            {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}}
        )
        return env

    def test_project_local_install_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            plugin = project / ".openharness" / "plugins" / "guard"
            for name in ("hooks", "lib", "policies"):
                shutil.copytree(ROOT / name, plugin / name)
            shutil.copy2(ROOT / "plugin.json", plugin / "plugin.json")

            result = subprocess.run(
                ["bash", "-lc", self.hook_command()],
                cwd=project,
                env=self.base_env(root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("destructive-rm-root", result.stderr)

    def test_missing_install_fails_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            result = subprocess.run(
                ["bash", "-lc", self.hook_command()],
                cwd=project,
                env=self.base_env(root),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("未找到 guard_hook.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
