"""邮箱通知：通过 SMTP 发送文本内容与本地文件附件。

只依赖 Python 标准库，供网关工具、hook 与测试复用。

配置优先级：环境变量 > 配置文件 > 默认值。

配置文件默认位置：``~/.openharness/guard-email.json``，可用
``OPENHARNESS_GUARD_EMAIL_CONFIG`` 覆盖。示例：

.. code-block:: json

    {
      "host": "smtp.example.com",
      "port": 587,
      "security": "starttls",
      "username": "bot@example.com",
      "password": "***",
      "from": "guard@example.com"
    }
"""

from __future__ import annotations

import json
import mimetypes
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

SECURITY_MODES = ("ssl", "starttls", "none")
_DEFAULT_PORTS = {"ssl": 465, "starttls": 587, "none": 25}


class MailError(RuntimeError):
    """配置错误、地址错误或发送失败。"""


@dataclass(frozen=True)
class SmtpSettings:
    """SMTP 连接参数。"""

    host: str
    port: int
    sender: str
    username: str | None = None
    password: str | None = None
    security: str = "starttls"
    timeout: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class Attachment:
    """一个待发送的附件。"""

    filename: str
    data: bytes
    maintype: str = "application"
    subtype: str = "octet-stream"


@dataclass(frozen=True)
class Email:
    """一封待发送的邮件。"""

    to: tuple[str, ...]
    subject: str
    body: str = ""
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    attachments: tuple[Attachment, ...] = ()


def default_config_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the default plugin config path, following OpenHarness's config dir."""
    base = (os.environ if env is None else env).get("OPENHARNESS_CONFIG_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".openharness"
    return root / "guard-email.json"


def _load_config_file(env: Mapping[str, str], config_path: str | Path | None) -> dict[str, Any]:
    explicit = config_path or env.get("OPENHARNESS_GUARD_EMAIL_CONFIG")
    path = Path(explicit).expanduser() if explicit else default_config_path(env)
    if not path.exists():
        if explicit:
            raise MailError(f"邮箱配置文件不存在：{path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MailError(f"无法读取邮箱配置文件 {path}：{exc}") from exc
    if not isinstance(data, dict):
        raise MailError(f"邮箱配置文件 {path} 顶层必须是对象")
    return data


def load_smtp_settings(
    env: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> SmtpSettings:
    """读取并校验 SMTP 配置。"""
    env = os.environ if env is None else env
    config = _load_config_file(env, config_path)

    def pick(env_key: str, config_key: str, default: Any = None) -> Any:
        value = env.get(env_key)
        if value not in (None, ""):
            return value
        value = config.get(config_key)
        return default if value is None else value

    host = str(pick("OPENHARNESS_GUARD_SMTP_HOST", "host", "") or "").strip()
    if not host:
        raise MailError(
            "未配置 SMTP 服务器。请设置 OPENHARNESS_GUARD_SMTP_HOST，"
            f"或写入 {default_config_path(env)}。"
        )

    security = str(pick("OPENHARNESS_GUARD_SMTP_SECURITY", "security", "starttls")).lower()
    if security not in SECURITY_MODES:
        raise MailError(f"security 必须是 {SECURITY_MODES} 之一，当前为 {security!r}")

    raw_port = pick("OPENHARNESS_GUARD_SMTP_PORT", "port", _DEFAULT_PORTS[security])
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise MailError(f"SMTP 端口无效：{raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise MailError(f"SMTP 端口超出范围：{port}")

    username = str(pick("OPENHARNESS_GUARD_SMTP_USER", "username", "") or "").strip() or None
    password = str(pick("OPENHARNESS_GUARD_SMTP_PASSWORD", "password", "") or "") or None
    if username and not password:
        raise MailError("已配置 SMTP 用户名但缺少密码（OPENHARNESS_GUARD_SMTP_PASSWORD）。")

    sender = str(pick("OPENHARNESS_GUARD_SMTP_FROM", "from", username or "") or "").strip()
    if not sender:
        raise MailError("缺少发件人地址（OPENHARNESS_GUARD_SMTP_FROM 或配置中的 from）。")
    if "@" not in sender or any(ch in sender for ch in "\r\n"):
        raise MailError(f"发件人地址无效：{sender!r}")

    raw_timeout = pick("OPENHARNESS_GUARD_SMTP_TIMEOUT", "timeout", DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise MailError(f"SMTP 超时时间无效：{raw_timeout!r}") from exc

    return SmtpSettings(
        host=host,
        port=port,
        sender=sender,
        username=username,
        password=password,
        security=security,
        timeout=timeout,
    )


def normalize_recipients(values: str | Sequence[str] | None) -> list[str]:
    """拆分、校验并去重收件人地址。"""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    result: list[str] = []
    for raw in values:
        for part in str(raw).split(","):
            candidate = part.strip()
            if not candidate:
                continue
            address = parseaddr(candidate)[1]
            if not address or "@" not in address or any(ch in address for ch in "\r\n"):
                raise MailError(f"无效的邮箱地址：{part!r}")
            if address not in result:
                result.append(address)
    return result


def parse_allowlist(raw: str | None) -> list[str]:
    """解析 ``a@b.com,@corp.com`` 形式的收件人白名单。"""
    if not raw:
        return []
    items = raw.replace(";", ",").split(",")
    return [item.strip().lower() for item in items if item.strip()]


def recipient_allowed(address: str, allowlist: Iterable[str]) -> bool:
    """白名单匹配：完整地址或 ``@domain``；空白名单表示不限制。"""
    patterns = [item.lower() for item in allowlist]
    if not patterns:
        return True
    normalized = address.strip().lower()
    domain = normalized.rsplit("@", 1)[-1]
    for pattern in patterns:
        if pattern.startswith("@"):
            if domain == pattern[1:]:
                return True
        elif normalized == pattern:
            return True
    return False


def attachment_limit(env: Mapping[str, str] | None = None) -> int:
    """读取附件总大小上限，默认 20 MiB。"""
    raw = (os.environ if env is None else env).get("OPENHARNESS_GUARD_EMAIL_MAX_BYTES")
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_MAX_ATTACHMENT_BYTES
    return value if value > 0 else DEFAULT_MAX_ATTACHMENT_BYTES


def collect_attachments(
    paths: Iterable[str | Path],
    cwd: str | Path | None = None,
    max_total_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
) -> list[Attachment]:
    """按路径读取附件；相对路径基于 ``cwd``。"""
    base = Path(cwd or ".").expanduser()
    attachments: list[Attachment] = []
    total = 0
    for raw in paths:
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
        if not path.is_file():
            raise MailError(f"附件不存在或不是文件：{path}")
        size = path.stat().st_size
        total += size
        if total > max_total_bytes:
            raise MailError(
                f"附件总大小超过上限（{max_total_bytes} 字节），在 {path.name} 处停止。"
            )
        guessed, _ = mimetypes.guess_type(path.name)
        if guessed and "/" in guessed:
            maintype, subtype = guessed.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        attachments.append(
            Attachment(
                filename=path.name.replace("\r", "").replace("\n", ""),
                data=path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
            )
        )
    return attachments


def build_message(settings: SmtpSettings, email: Email) -> EmailMessage:
    """构造 MIME 邮件，供发送与测试使用。"""
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = ", ".join(email.to)
    if email.cc:
        message["Cc"] = ", ".join(email.cc)
    message["Subject"] = " ".join(str(email.subject).splitlines()) or "(无主题)"
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(email.body or "")
    for attachment in email.attachments:
        message.add_attachment(
            attachment.data,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )
    return message


def _default_smtp_factory(settings: SmtpSettings):
    if settings.security == "ssl":
        return smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout)
    return smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)


def verify_connection(
    settings: SmtpSettings | None = None,
    *,
    smtp_factory=None,
) -> None:
    """只连接、握手并登录，不发送邮件；失败抛出 :class:`MailError`。"""
    settings = settings or load_smtp_settings()
    factory = smtp_factory or _default_smtp_factory
    try:
        client = factory(settings)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"无法连接 SMTP 服务器 {settings.host}:{settings.port}：{exc}") from exc
    try:
        client.ehlo()
        if settings.security == "starttls":
            client.starttls()
            client.ehlo()
        if settings.username and settings.password:
            client.login(settings.username, settings.password)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"SMTP 连接或登录失败：{exc}") from exc
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - 连接可能已断开
            pass


def send(
    email: Email,
    settings: SmtpSettings | None = None,
    *,
    smtp_factory=None,
) -> dict[str, Any]:
    """发送邮件并返回摘要；失败抛出 :class:`MailError`。"""
    settings = settings or load_smtp_settings()
    recipients = list(email.to) + list(email.cc) + list(email.bcc)
    if not email.to:
        raise MailError("至少需要一个收件人。")

    message = build_message(settings, email)
    factory = smtp_factory or _default_smtp_factory
    try:
        client = factory(settings)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"无法连接 SMTP 服务器 {settings.host}:{settings.port}：{exc}") from exc
    try:
        client.ehlo()
        if settings.security == "starttls":
            client.starttls()
            client.ehlo()
        if settings.username and settings.password:
            client.login(settings.username, settings.password)
        client.send_message(message, from_addr=settings.sender, to_addrs=recipients)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"SMTP 发送失败：{exc}") from exc
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - 连接可能已断开
            pass

    return {
        "sent": True,
        "host": settings.host,
        "from": settings.sender,
        "to": list(email.to),
        "cc": list(email.cc),
        "bcc_count": len(email.bcc),
        "subject": message["Subject"],
        "attachments": [attachment.filename for attachment in email.attachments],
        "size_bytes": len(message.as_bytes()),
    }
