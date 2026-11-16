"""scripts/uninstall.sh 与 scripts/update.sh 的端到端测试。

和 test_install_script.py 一样：装到临时插件根，再跑真实脚本，验证结果落在磁盘上。
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
INSTALL = ROOT / "scripts" / "install.sh"
UNINSTALL = ROOT / "scripts" / "uninstall.sh"
UPDATE = ROOT / "scripts" / "update.sh"
BASH = shutil.which("bash")
TAR = shutil.which("tar")


@unittest.skipUnless(BASH and TAR, "生命周期脚本需要 bash 与 tar")
class LifecycleScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.dest = self.root / "plugins"

    # --- helpers -----------------------------------------------------

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OPENHARNESS_") and key != "OHMO_WORKSPACE"
        }
        env["HOME"] = str(self.root / "home")
        return subprocess.run(
            [BASH, str(script), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def install(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_script(INSTALL, *args, str(self.dest))

    def uninstall(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_script(UNINSTALL, *args, str(self.dest))

    def update(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_script(UPDATE, *args, str(self.dest))

    # --- uninstall ---------------------------------------------------

    def test_uninstall_removes_only_selected_plugin(self) -> None:
        self.install("--only", "guard,guard-email")
        result = self.uninstall("--only", "guard")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.dest / "guard").exists())
        self.assertTrue((self.dest / "guard-email" / "plugin.json").is_file())

    def test_uninstall_all_plugins(self) -> None:
        self.install("--only", "guard,guard-email")
        result = self.uninstall()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p.name for p in self.dest.iterdir()], [])

    def test_uninstall_dry_run_keeps_files(self) -> None:
        self.install("--only", "guard")
        result = self.uninstall("--dry-run", "--only", "guard")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("演练模式", result.stdout)
        self.assertTrue((self.dest / "guard" / "plugin.json").is_file())

    def test_uninstall_skips_foreign_directory(self) -> None:
        foreign = self.dest / "guard"
        foreign.mkdir(parents=True)
        (foreign / "plugin.json").write_text(
            json.dumps({"name": "not-guard", "version": "9.9.9"}), encoding="utf-8"
        )

        result = self.uninstall("--only", "guard")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("不是本仓库的插件", result.stderr)
        self.assertTrue((foreign / "plugin.json").is_file())

    @unittest.skipIf(os.name == "nt", "Windows 下软链接需要额外权限")
    def test_uninstall_removes_symlink_but_keeps_repo(self) -> None:
        self.install("--link", "--only", "guard")
        self.assertTrue((self.dest / "guard").is_symlink())

        result = self.uninstall("--only", "guard")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.dest / "guard").exists())
        self.assertTrue((ROOT / "plugins" / "guard" / "plugin.json").is_file())

    def test_uninstall_list_reports_state(self) -> None:
        self.install("--only", "guard")
        result = self.uninstall("--list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("guard", result.stdout)
        self.assertIn("复制", result.stdout)
        self.assertIn("未安装", result.stdout)  # ask_image 没装
        self.assertTrue((self.dest / "guard" / "plugin.json").is_file())

    # --- update ------------------------------------------------------

    def test_update_reinstalls_copy_install(self) -> None:
        self.install("--only", "guard")
        marker = self.dest / "guard" / "MARKER"
        marker.write_text("stale", encoding="utf-8")

        result = self.update()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("更新 guard", result.stdout)
        self.assertFalse(marker.exists(), "重装应清掉旧文件")

    def test_update_does_not_install_missing_plugins(self) -> None:
        self.install("--only", "guard")

        result = self.update()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("未安装", result.stdout)
        self.assertFalse((self.dest / "ask_image").exists())

    @unittest.skipIf(os.name == "nt", "Windows 下软链接需要额外权限")
    def test_update_skips_symlink_install(self) -> None:
        self.install("--link", "--only", "guard")

        result = self.update()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("软链接安装", result.stdout)
        self.assertTrue((self.dest / "guard").is_symlink())

    def test_update_dry_run_changes_nothing(self) -> None:
        self.install("--only", "guard")
        marker = self.dest / "guard" / "MARKER"
        marker.write_text("stale", encoding="utf-8")

        result = self.update("--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("演练模式", result.stdout)
        self.assertTrue(marker.exists())

    def test_update_skips_foreign_directory(self) -> None:
        foreign = self.dest / "guard"
        foreign.mkdir(parents=True)
        (foreign / "plugin.json").write_text(
            json.dumps({"name": "not-guard", "version": "9.9.9"}), encoding="utf-8"
        )

        result = self.update("--only", "guard")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("不是本仓库的插件", result.stderr)
        self.assertTrue((foreign / "plugin.json").is_file())


if __name__ == "__main__":
    unittest.main()
