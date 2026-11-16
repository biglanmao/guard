"""插件集合布局与 hook 集成测试。"""

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
PLUGINS = ROOT / "plugins"
GUARD = PLUGINS / "guard"
GUARD_EMAIL = PLUGINS / "guard-email"


def discover_plugins() -> list[Path]:
    """返回 plugins/ 下所有带 plugin.json 的插件目录。"""
    return sorted(path for path in PLUGINS.glob("*/plugin.json"))


class PluginCollectionTest(unittest.TestCase):
    def test_plugins_directory_exists(self) -> None:
        self.assertTrue(PLUGINS.is_dir(), "仓库根应为插件集合，插件放在 plugins/<名称>/")

    def test_every_plugin_has_valid_manifest(self) -> None:
        manifests = discover_plugins()
        self.assertTrue(manifests, "plugins/ 下没有任何插件")
        names = []
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            plugin_root = manifest_path.parent
            self.assertEqual(
                manifest["name"],
                plugin_root.name,
                f"{manifest_path} 的 name 必须与目录名一致（安装脚本依赖该约定）",
            )
            self.assertTrue(manifest["version"], f"{plugin_root} 缺少 version")
            self.assertTrue(manifest["description"], f"{plugin_root} 缺少 description")
            for key in ("skills_dir", "tools_dir", "hooks_file", "mcp_file"):
                if key in manifest:
                    self.assertTrue(
                        (plugin_root / manifest[key]).exists(),
                        f"{plugin_root} 缺少 {manifest[key]}",
                    )
            names.append(manifest["name"])
        self.assertEqual(len(names), len(set(names)), "插件名称重复")

    def test_each_plugin_is_self_contained(self) -> None:
        """插件必须能单独安装：清单里的路径不得指向插件目录之外。"""
        for manifest_path in discover_plugins():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            plugin_root = manifest_path.parent.resolve()
            for key in (
                "skills_dir",
                "tools_dir",
                "hooks_file",
                "mcp_file",
                "commands",
                "agents",
                "skills",
            ):
                value = manifest.get(key)
                if not isinstance(value, str):
                    continue
                target = (plugin_root / value).resolve()
                self.assertTrue(
                    str(target).startswith(str(plugin_root) + "/"),
                    f"{plugin_root.name}.{key}={value} 指向了插件目录之外",
                )
                if key.endswith("_dir") or not Path(value).suffix:
                    self.assertTrue(
                        target.is_dir(), f"{plugin_root.name} 缺少目录 {value}"
                    )
                else:
                    self.assertTrue(
                        target.is_file(), f"{plugin_root.name} 缺少文件 {value}"
                    )

    def test_repository_root_is_not_a_plugin(self) -> None:
        self.assertFalse(
            (ROOT / "plugin.json").exists(),
            "根目录不应再有 plugin.json：仓库根是插件集合，不是单个插件",
        )


class PluginLayoutTest(unittest.TestCase):
    def test_manifest(self) -> None:
        manifest = json.loads((GUARD / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "guard")
        self.assertTrue(manifest["version"])
        self.assertTrue(manifest["description"])
        for key in ("skills_dir", "tools_dir", "hooks_file", "mcp_file"):
            self.assertTrue((GUARD / manifest[key]).exists(), f"缺少 {manifest[key]}")

    def test_extension_points_exist(self) -> None:
        self.assertTrue((GUARD / "skills" / "guard-safety" / "SKILL.md").is_file())
        self.assertTrue((GUARD / "commands" / "audit.md").is_file())
        self.assertTrue((GUARD / "agents" / "guard-reviewer.md").is_file())
        self.assertTrue((GUARD / "tools" / "guard_check.py").is_file())
        self.assertTrue((GUARD / "hooks" / "guard_hook.py").is_file())
        self.assertTrue((GUARD / "hooks" / "guard_audit.py").is_file())
        self.assertTrue((GUARD / "policies" / "default.json").is_file())

    def test_guard_email_plugin_layout(self) -> None:
        self.assertTrue((GUARD_EMAIL / "tools" / "send_email.py").is_file())
        self.assertTrue((GUARD_EMAIL / "lib" / "mailer.py").is_file())
        self.assertTrue((GUARD_EMAIL / "scripts" / "guard-config.py").is_file())
        self.assertTrue((GUARD_EMAIL / "commands" / "email.md").is_file())
        self.assertTrue((GUARD_EMAIL / "examples" / "guard-email.example.json").is_file())
        manifest = json.loads((GUARD_EMAIL / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "guard-email")
        self.assertEqual(manifest.get("tools_dir", "tools"), "tools")

    def test_email_capability_is_not_in_guard(self) -> None:
        """邮箱能力独立成插件：guard 里不应残留邮件相关实现。"""
        for relative in (
            "tools/send_email.py",
            "lib/mailer.py",
            "scripts/guard-config.py",
            "commands/email.md",
            "examples/guard-email.example.json",
        ):
            self.assertFalse((GUARD / relative).exists(), f"guard 仍包含 {relative}")
        for path in GUARD.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("import mailer", source, f"{path} 仍然依赖 mailer")

    def test_email_rules_stay_in_guard_policy(self) -> None:
        """邮箱规则留在 guard 的策略里（按工具名匹配，未装 guard-email 时不命中）。"""
        policy = json.loads((GUARD / "policies" / "default.json").read_text(encoding="utf-8"))
        rule_ids = {rule["id"] for rule in policy["rules"]}
        self.assertIn("email-sensitive-attachment", rule_ids)
        self.assertIn("leak-smtp-secret", rule_ids)

    def test_hooks_configuration(self) -> None:
        hooks = json.loads((GUARD / "hooks.json").read_text(encoding="utf-8"))
        pre = hooks["pre_tool_use"]
        self.assertEqual(pre[0]["type"], "command")
        self.assertTrue(pre[0]["block_on_failure"])
        self.assertIn("guard_hook.py", pre[0]["command"])
        self.assertEqual(pre[0]["priority"], 100)
        self.assertIn("$PWD/.openharness/plugins", pre[0]["command"])
        self.assertIn("${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins", pre[0]["command"])
        self.assertIn("${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins", pre[0]["command"])
        # 多插件布局下插件目录名可以变化，hook 必须按通配符定位而不是写死 plugins/guard。
        self.assertIn("*/hooks/guard_hook.py", pre[0]["command"])
        self.assertNotIn("plugins/guard", pre[0]["command"])
        post = hooks["post_tool_use"][0]
        self.assertFalse(post["block_on_failure"])
        self.assertIn("*/hooks/guard_audit.py", post["command"])

    def test_mcp_configuration(self) -> None:
        mcp = json.loads((GUARD / "mcp.json").read_text(encoding="utf-8"))
        self.assertIsInstance(mcp["mcpServers"], dict)

    def test_installer_discovers_plugins(self) -> None:
        script = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
        self.assertIn('SRC_PLUGINS="$SRC/plugins"', script)
        self.assertIn('"$SRC_PLUGINS"/*/', script)

    def test_installer_supports_selective_install(self) -> None:
        """插件彼此独立：安装脚本必须支持列出与只装指定插件。"""
        script = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
        for flag in ("--list", "--only", "--all"):
            self.assertIn(flag, script)


class HookIntegrationTest(unittest.TestCase):
    def run_hook(self, payload: dict, **env_overrides: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "OPENHARNESS_HOOK_PAYLOAD": json.dumps(payload),
            **env_overrides,
        }
        return subprocess.run(
            [sys.executable, str(GUARD / "hooks" / "guard_hook.py")],
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
    """hooks.json 的命令必须能在各种安装位置（插件根或插件根目录）找到脚本。"""

    def hook_command(self) -> str:
        hooks = json.loads((GUARD / "hooks.json").read_text(encoding="utf-8"))
        return hooks["pre_tool_use"][0]["command"]

    def base_env(self, root: Path, **overrides: str) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "OPENHARNESS_CONFIG_DIR",
                "OPENHARNESS_GUARD_ROOT",
                "OPENHARNESS_GUARD_POLICY",
                "OPENHARNESS_GUARD_MODE",
                "OHMO_WORKSPACE",
            }
        }
        env["HOME"] = str(root / "home")
        env["OPENHARNESS_HOOK_PAYLOAD"] = json.dumps(
            {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}}
        )
        env.update(overrides)
        return env

    def install_copy(self, plugin: Path) -> None:
        for name in ("hooks", "lib", "policies"):
            shutil.copytree(GUARD / name, plugin / name)
        shutil.copy2(GUARD / "plugin.json", plugin / "plugin.json")

    def run_command(
        self, root: Path, project: Path, **overrides: str
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", self.hook_command()],
            cwd=project,
            env=self.base_env(root, **overrides),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def assert_blocked(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("destructive-rm-root", result.stderr)

    def test_user_level_install_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            self.install_copy(root / "home" / ".openharness" / "plugins" / "guard")
            self.assert_blocked(self.run_command(root, project))

    def test_custom_config_dir_install_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            plugins = root / "custom" / "plugins"
            self.install_copy(plugins / "guard")
            self.assert_blocked(
                self.run_command(root, project, OPENHARNESS_CONFIG_DIR=str(plugins.parent))
            )

    def test_project_local_install_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            self.install_copy(project / ".openharness" / "plugins" / "guard")
            self.assert_blocked(self.run_command(root, project))

    def test_ohmo_workspace_install_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            self.install_copy(root / "home" / ".ohmo" / "plugins" / "guard")
            self.assert_blocked(self.run_command(root, project))

    def test_plugin_root_override_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            plugin = root / "elsewhere" / "guard"
            self.install_copy(plugin)
            self.assert_blocked(
                self.run_command(root, project, OPENHARNESS_GUARD_ROOT=str(plugin))
            )

    def test_plugins_root_override_is_found(self) -> None:
        """OPENHARNESS_GUARD_ROOT 指向插件根目录（多插件布局）时也应命中。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            plugins = root / "elsewhere"
            self.install_copy(plugins / "guard")
            self.assert_blocked(
                self.run_command(root, project, OPENHARNESS_GUARD_ROOT=str(plugins))
            )

    def test_missing_install_fails_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            result = self.run_command(root, project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("未找到 guard_hook.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
