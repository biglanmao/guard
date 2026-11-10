#!/usr/bin/env python3
"""guard 邮箱配置向导：交互式写入 SMTP 配置并测试连接。

用法：
  python3 scripts/guard-config.py setup     # 交互式配置并测试
  python3 scripts/guard-config.py show      # 查看非敏感配置
  python3 scripts/guard-config.py test      # 只测试连接与登录
  python3 scripts/guard-config.py test --send-to you@example.com  # 发测试邮件

配置默认写入 ``${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/guard-email.json``，
文件权限设为 600。授权码通过 getpass 隐藏输入，不会回显、不会写入 shell 历史。
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

from mailer import (  # noqa: E402
    Email,
    MailError,
    default_config_path,
    load_smtp_settings,
    send,
    verify_connection,
)

PRESETS = {
    "qq": {"host": "smtp.qq.com", "port": 465, "security": "ssl"},
    "163": {"host": "smtp.163.com", "port": 465, "security": "ssl"},
    "126": {"host": "smtp.126.com", "port": 465, "security": "ssl"},
    "gmail": {"host": "smtp.gmail.com", "port": 587, "security": "starttls"},
    "outlook": {"host": "smtp.office365.com", "port": 587, "security": "starttls"},
    "custom": {},
}
SECURITY_CHOICES = ("ssl", "starttls", "none")
PROVIDER_HINTS = {
    "qq": "QQ 邮箱：设置 → 账户 → 开启 POP3/SMTP 服务 → 生成 16 位授权码（不是 QQ 密码）",
    "163": "163 邮箱：设置 → POP3/SMTP/IMAP → 开启 SMTP → 获取授权码",
    "126": "126 邮箱：设置 → POP3/SMTP/IMAP → 开启 SMTP → 获取授权码",
    "gmail": "Gmail：开启两步验证后生成「应用专用密码」",
    "outlook": "Outlook/M365：使用应用密码；若租户禁用基本认证，需改用 OAuth",
    "custom": "使用企业邮箱或自建 SMTP：向管理员索取主机、端口与认证方式",
}


def resolve_path(raw: str | None) -> Path:
    return Path(raw).expanduser() if raw else default_config_path()


def read_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MailError(f"无法读取 {path}：{exc}") from exc
    if not isinstance(data, dict):
        raise MailError(f"{path} 顶层必须是 JSON 对象")
    return data


def write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    os.replace(temp, path)


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default not in (None, ""):
            return str(default)
        print("  不能为空，请重新输入。")


def ask_port(default: int | None) -> int:
    while True:
        raw = ask("端口", str(default) if default else None)
        try:
            port = int(raw)
        except ValueError:
            print("  端口必须是数字。")
            continue
        if 1 <= port <= 65535:
            return port
        print("  端口必须在 1-65535 之间。")


def ask_security(default: str | None) -> str:
    hint = "/".join(SECURITY_CHOICES)
    while True:
        value = ask(f"加密方式 ({hint})", default).lower()
        if value in SECURITY_CHOICES:
            return value
        print(f"  只能是 {hint}。")


def cmd_setup(args: argparse.Namespace) -> int:
    path = resolve_path(args.config)
    existing = read_config(path)

    interactive = not (
        args.from_env
        or any(
            [
                args.host,
                args.port,
                args.security,
                args.username,
                args.from_address,
                args.password_env,
            ]
        )
    )

    if path.exists() and not args.force:
        if interactive:
            answer = input(f"{path} 已存在，更新它吗？[y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("已取消。")
                return 1
        else:
            print(f"{path} 已存在；非交互覆盖请加 --force。", file=sys.stderr)
            return 1

    provider = args.provider
    if interactive and not provider:
        choices = "/".join(PRESETS)
        provider = ask(f"邮箱服务商 ({choices})", "qq").lower()
    provider = provider or "custom"
    if provider not in PRESETS:
        print(f"未知服务商：{provider}，可选：{', '.join(PRESETS)}", file=sys.stderr)
        return 1

    preset = PRESETS[provider]
    if interactive:
        print(f"\n{PROVIDER_HINTS[provider]}\n")

    def resolve(field: str, cli_value, env_name: str, label: str, default) -> str:
        if cli_value not in (None, ""):
            return str(cli_value)
        if args.from_env:
            env_value = os.environ.get(env_name)
            if env_value not in (None, ""):
                return str(env_value)
        if interactive:
            return ask(label, existing.get(field) or default)
        if existing.get(field) not in (None, ""):
            return str(existing[field])
        return "" if default in (None, "") else str(default)

    host = resolve("host", args.host, "OPENHARNESS_GUARD_SMTP_HOST", "SMTP 主机", preset.get("host"))
    raw_port = resolve(
        "port", args.port, "OPENHARNESS_GUARD_SMTP_PORT", "端口", preset.get("port")
    )
    security = resolve(
        "security",
        args.security,
        "OPENHARNESS_GUARD_SMTP_SECURITY",
        "加密方式",
        preset.get("security"),
    ).lower()
    username = resolve(
        "username",
        args.username,
        "OPENHARNESS_GUARD_SMTP_USER",
        "邮箱账号（完整地址）",
        "",
    )
    sender = resolve(
        "from",
        args.from_address,
        "OPENHARNESS_GUARD_SMTP_FROM",
        "发件人地址",
        username,
    )

    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        print(f"端口无效：{raw_port!r}", file=sys.stderr)
        return 1
    if not 1 <= port <= 65535:
        print(f"端口超出范围：{port}", file=sys.stderr)
        return 1
    if security not in SECURITY_CHOICES:
        print(f"加密方式必须是 {'/'.join(SECURITY_CHOICES)}", file=sys.stderr)
        return 1

    password_env = args.password_env
    if args.from_env and not password_env:
        password_env = "OPENHARNESS_GUARD_SMTP_PASSWORD"

    if password_env:
        password = os.environ.get(password_env, "").strip()
        if not password:
            print(f"环境变量 {password_env} 未设置或为空。", file=sys.stderr)
            return 1
    elif interactive:
        if not sys.stdin.isatty():
            print("非交互环境无法安全读取授权码；请使用 --password-env 或 --from-env。", file=sys.stderr)
            return 1
        password = getpass.getpass("SMTP 授权码/密码（留空保留原值）: ").strip()
        if not password:
            password = str(existing.get("password") or "")
    else:
        password = str(existing.get("password") or "")
    if not password:
        print(
            "缺少授权码：非交互模式请用 --password-env <变量名> 或 --from-env。",
            file=sys.stderr,
        )
        return 1

    missing = [name for name, value in (("host", host), ("username", username), ("from", sender)) if not value]
    if missing:
        print("缺少必填字段：" + "、".join(missing), file=sys.stderr)
        return 1

    timeout = existing.get("timeout", 30)
    data = {
        "host": host,
        "port": port,
        "security": security,
        "username": username,
        "password": password,
        "from": sender,
        "timeout": timeout,
    }
    write_config(path, data)
    source = f"环境变量 {password_env}" if password_env else "交互输入"
    print(f"\n已写入 {path}（权限 600），授权码来源：{source}。")

    if args.no_test:
        return 0

    try:
        # 校验刚写入的文件本身，避免被当前 shell 里的 SMTP 环境变量掩盖。
        file_env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OPENHARNESS_GUARD_SMTP_")
        }
        settings = load_smtp_settings(file_env, config_path=path)
        verify_connection(settings)
        print(f"SMTP 连接与登录成功：{settings.host}:{settings.port} ({settings.security})")
        if args.send_to:
            result = send(
                Email(
                    to=(args.send_to,),
                    subject="guard SMTP 测试",
                    body="这是一封来自 guard 的 SMTP 测试邮件。",
                ),
                settings,
            )
            print(f"测试邮件已发送到 {args.send_to}（{result['size_bytes']} 字节）。")
    except MailError as exc:
        print(f"配置已保存，但连接测试失败：{exc}", file=sys.stderr)
        return 1
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = resolve_path(args.config)
    if not path.exists():
        print(f"尚未配置：{path}")
        print(f"运行：python3 {Path(__file__).resolve()} setup")
        return 0
    data = read_config(path)
    mode = path.stat().st_mode & 0o777
    print(f"配置文件：{path}（权限 {mode:o}）")
    for key in ("host", "port", "security", "username", "from", "timeout"):
        if key in data:
            print(f"  {key}: {data[key]}")
    print(f"  password: {'已设置' if data.get('password') else '未设置'}")
    overrides = [name for name in os.environ if name.startswith("OPENHARNESS_GUARD_SMTP_")]
    if overrides:
        print("环境变量覆盖：" + ", ".join(sorted(overrides)))
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    path = resolve_path(args.config)
    try:
        settings = load_smtp_settings(config_path=path)
        verify_connection(settings)
        print(f"SMTP 连接与登录成功：{settings.host}:{settings.port} ({settings.security})")
        if args.send_to:
            result = send(
                Email(
                    to=(args.send_to,),
                    subject="guard SMTP 测试",
                    body="这是一封来自 guard 的 SMTP 测试邮件。",
                ),
                settings,
            )
            print(f"测试邮件已发送到 {args.send_to}（{result['size_bytes']} 字节）。")
    except MailError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="配置 guard 的 SMTP 邮箱通知")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="交互式配置并测试 SMTP")
    setup.add_argument("--config", help="配置文件路径")
    setup.add_argument("--provider", choices=sorted(PRESETS), help="邮箱服务商预设")
    setup.add_argument("--host", help="SMTP 主机（非交互）")
    setup.add_argument("--port", help="SMTP 端口（非交互）")
    setup.add_argument("--security", choices=SECURITY_CHOICES, help="加密方式（非交互）")
    setup.add_argument("--username", help="邮箱账号（非交互）")
    setup.add_argument("--from", dest="from_address", help="发件人地址（非交互）")
    setup.add_argument("--password-env", metavar="VAR", help="从该环境变量读取授权码，避免明文上命令行")
    setup.add_argument("--from-env", action="store_true", help="从 OPENHARNESS_GUARD_SMTP_* 读取全部字段")
    setup.add_argument("--force", action="store_true", help="覆盖已有配置，不再询问")
    setup.add_argument("--no-test", action="store_true", help="只写配置，不测试连接")
    setup.add_argument("--send-to", help="配置成功后发送一封测试邮件到该地址")
    setup.set_defaults(func=cmd_setup)

    show = sub.add_parser("show", help="查看配置（不显示密码）")
    show.add_argument("--config", help="配置文件路径")
    show.set_defaults(func=cmd_show)

    test = sub.add_parser("test", help="测试 SMTP 连接与登录")
    test.add_argument("--config", help="配置文件路径")
    test.add_argument("--send-to", help="测试成功后发送测试邮件到该地址")
    test.set_defaults(func=cmd_test)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 1
    except MailError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
