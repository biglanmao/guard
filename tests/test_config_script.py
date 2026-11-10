"""scripts/guard-config.py 的行为测试。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "guard-config.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("guard_config_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConfigScriptTest(unittest.TestCase):
    def run_script(
        self, *args: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OPENHARNESS_GUARD_SMTP_")
        }
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )

    def test_help(self) -> None:
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("setup", result.stdout)

    def test_show_masks_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard-email.json"
            path.write_text(
                json.dumps(
                    {
                        "host": "smtp.example.com",
                        "port": 465,
                        "security": "ssl",
                        "username": "bot@example.com",
                        "password": "super-secret-auth-code",
                        "from": "bot@example.com",
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script("show", "--config", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("smtp.example.com", result.stdout)
            self.assertIn("已设置", result.stdout)
            self.assertNotIn("super-secret-auth-code", result.stdout)

    def test_show_missing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script("show", "--config", str(Path(tmp) / "nope.json"))
            self.assertEqual(result.returncode, 0)
            self.assertIn("尚未配置", result.stdout)

    def test_write_config_is_private(self) -> None:
        module = load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "guard-email.json"
            module.write_config(path, {"host": "smtp.example.com", "password": "x"})
            self.assertTrue(path.exists())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["host"], "smtp.example.com")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_setup_from_env_writes_config_without_echoing_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard-email.json"
            result = self.run_script(
                "setup",
                "--from-env",
                "--no-test",
                "--config",
                str(path),
                extra_env={
                    "OPENHARNESS_GUARD_SMTP_HOST": "smtp.example.com",
                    "OPENHARNESS_GUARD_SMTP_PORT": "465",
                    "OPENHARNESS_GUARD_SMTP_SECURITY": "ssl",
                    "OPENHARNESS_GUARD_SMTP_USER": "bot@example.com",
                    "OPENHARNESS_GUARD_SMTP_PASSWORD": "auth-code-secret",
                    "OPENHARNESS_GUARD_SMTP_FROM": "bot@example.com",
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("auth-code-secret", result.stdout + result.stderr)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["password"], "auth-code-secret")
            self.assertEqual(data["host"], "smtp.example.com")

    def test_setup_password_env_keeps_secret_off_command_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard-email.json"
            result = self.run_script(
                "setup",
                "--host",
                "smtp.example.com",
                "--port",
                "587",
                "--security",
                "starttls",
                "--username",
                "bot@example.com",
                "--from",
                "bot@example.com",
                "--password-env",
                "MY_SMTP_CODE",
                "--no-test",
                "--config",
                str(path),
                extra_env={"MY_SMTP_CODE": "hidden-code"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("hidden-code", result.stdout + result.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["password"], "hidden-code")

    def test_setup_requires_a_password_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard-email.json"
            result = self.run_script(
                "setup",
                "--host",
                "smtp.example.com",
                "--port",
                "587",
                "--security",
                "starttls",
                "--username",
                "bot@example.com",
                "--from",
                "bot@example.com",
                "--no-test",
                "--config",
                str(path),
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("password-env", result.stderr)
            self.assertFalse(path.exists())

    def test_setup_non_interactive_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard-email.json"
            path.write_text("{}", encoding="utf-8")
            result = self.run_script(
                "setup",
                "--host",
                "smtp.example.com",
                "--port",
                "587",
                "--security",
                "starttls",
                "--username",
                "bot@example.com",
                "--from",
                "bot@example.com",
                "--password-env",
                "MY_SMTP_CODE",
                "--no-test",
                "--config",
                str(path),
                extra_env={"MY_SMTP_CODE": "hidden-code"},
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("--force", result.stderr)

    def test_invalid_config_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard-email.json"
            path.write_text("{oops", encoding="utf-8")
            result = self.run_script("show", "--config", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("无法读取", result.stderr)


if __name__ == "__main__":
    unittest.main()
