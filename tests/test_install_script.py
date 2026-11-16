"""scripts/install.sh 的端到端测试。

装到临时插件根后，直接用安装产物的 `hooks.json` 跑真实命令，验证「装 -> 找 ->
拦」这条链路，而不是只检查文件是否存在。

需要 bash 与 tar（安装脚本自身依赖），缺失时整类跳过。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.sh"
BASH = shutil.which("bash")
TAR = shutil.which("tar")

DANGEROUS = {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}}
BENIGN = {"tool_name": "bash", "tool_input": {"command": "ls -la"}}


@unittest.skipUnless(BASH and TAR, "安装脚本需要 bash 与 tar")
class InstallScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.dest = self.root / "plugins"
        self.project = self.root / "project"
        self.project.mkdir()

    # --- helpers -----------------------------------------------------

    def install(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [BASH, str(INSTALLER), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def hook_command(self, event: str) -> str:
        hooks = json.loads((self.dest / "guard" / "hooks.json").read_text(encoding="utf-8"))
        return hooks[event][0]["command"]

    def run_hook(
        self,
        event: str,
        payload: dict,
        **env_overrides: str,
    ) -> subprocess.CompletedProcess:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OPENHARNESS_")
        }
        env.update(
            {
                "HOME": str(self.root / "home"),
                "OPENHARNESS_GUARD_ROOT": str(self.dest / "guard"),
                "OPENHARNESS_HOOK_PAYLOAD": json.dumps(payload),
                **env_overrides,
            }
        )
        return subprocess.run(
            [BASH, "-c", self.hook_command(event)],
            cwd=self.project,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    # --- tests -------------------------------------------------------

    def test_install_only_selected_plugins(self) -> None:
        result = self.install("--only", "guard", str(self.dest))
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertTrue((self.dest / "guard" / "plugin.json").is_file())
        self.assertTrue((self.dest / "guard" / "hooks" / "guard_hook.py").is_file())
        self.assertFalse(
            (self.dest / "guard-email").exists(),
            "--only guard 不应该顺带装上 guard-email",
        )

    def test_install_marks_hook_scripts_executable(self) -> None:
        result = self.install("--only", "guard,guard-email", str(self.dest))
        self.assertEqual(result.returncode, 0, result.stderr)

        for script in (
            self.dest / "guard" / "hooks" / "guard_hook.py",
            self.dest / "guard" / "hooks" / "guard_audit.py",
            self.dest / "guard-email" / "scripts" / "guard-config.py",
        ):
            self.assertTrue(os.access(script, os.X_OK), f"{script} 缺少可执行位")

    def test_installed_hook_blocks_and_allows(self) -> None:
        self.install("--only", "guard", str(self.dest))

        blocked = self.run_hook("pre_tool_use", DANGEROUS)
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertIn("destructive-rm-root", blocked.stderr)

        allowed = self.run_hook("pre_tool_use", BENIGN)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertNotIn("[guard][WARN]", allowed.stderr)

    def test_installed_audit_hook_writes_record(self) -> None:
        self.install("--only", "guard", str(self.dest))

        result = self.run_hook("post_tool_use", BENIGN)
        self.assertEqual(result.returncode, 0, result.stderr)

        log = self.root / "home" / ".openharness" / "logs" / "guard-audit.jsonl"
        self.assertTrue(log.is_file(), result.stderr)
        records = [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(records[-1]["event"], "post_tool_use")
        self.assertEqual(records[-1]["tool_name"], "bash")

    @unittest.skipIf(os.name == "nt", "Windows 下软链接需要额外权限")
    def test_link_install_works(self) -> None:
        result = self.install("--link", "--only", "guard", str(self.dest))
        self.assertEqual(result.returncode, 0, result.stderr)

        installed = self.dest / "guard"
        self.assertTrue(installed.is_symlink())
        self.assertEqual(installed.resolve(), (ROOT / "plugins" / "guard").resolve())

        blocked = self.run_hook("pre_tool_use", DANGEROUS)
        self.assertEqual(blocked.returncode, 2, blocked.stderr)

    def test_existing_install_requires_force(self) -> None:
        first = self.install("--only", "guard", str(self.dest))
        self.assertEqual(first.returncode, 0, first.stderr)

        second = self.install("--only", "guard", str(self.dest))
        self.assertEqual(second.returncode, 1)
        self.assertIn("已存在", second.stderr)

        forced = self.install("--force", "--only", "guard", str(self.dest))
        self.assertEqual(forced.returncode, 0, forced.stderr)

    def test_list_reports_every_plugin(self) -> None:
        result = self.install("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("guard", "guard-email", "ask_image"):
            self.assertIn(name, result.stdout)


if __name__ == "__main__":
    unittest.main()
