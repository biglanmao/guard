"""send_email 工具：通过 SMTP 把文本与本地文件附件发送到指定邮箱。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT / "lib"))


class SendEmailInput(BaseModel):
    """send_email 的参数。"""

    to: list[str] = Field(description="收件人邮箱地址列表")
    subject: str = Field(description="邮件主题")
    body: str = Field(default="", description="邮件正文（纯文本）")
    attachments: list[str] = Field(
        default_factory=list,
        description="要附加的本地文件路径列表；相对路径基于当前工作目录",
    )
    cc: list[str] = Field(default_factory=list, description="抄送地址列表")
    bcc: list[str] = Field(default_factory=list, description="密送地址列表")


class SendEmailTool(BaseTool):
    """发送带附件的邮件通知。"""

    name = "send_email"
    description = (
        "通过 SMTP 把文本内容和本地文件附件发送到指定邮箱。"
        "需要预先配置 SMTP 环境变量或 ~/.openharness/guard-email.json；"
        "发送是外部副作用，请确认收件人与附件内容。"
    )
    input_model = SendEmailInput

    async def execute(
        self,
        arguments: SendEmailInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        from mailer import (
            Email,
            MailError,
            attachment_limit,
            collect_attachments,
            load_smtp_settings,
            normalize_recipients,
            parse_allowlist,
            recipient_allowed,
            send,
        )

        try:
            to = normalize_recipients(arguments.to)
            cc = normalize_recipients(arguments.cc)
            bcc = normalize_recipients(arguments.bcc)
            if not to:
                raise MailError("至少需要一个收件人（to）。")

            allowlist = parse_allowlist(os.environ.get("OPENHARNESS_GUARD_EMAIL_ALLOWLIST"))
            blocked = [
                address
                for address in [*to, *cc, *bcc]
                if not recipient_allowed(address, allowlist)
            ]
            if blocked:
                raise MailError(
                    "以下收件人不在白名单内：" + "、".join(blocked)
                    + "。请调整 OPENHARNESS_GUARD_EMAIL_ALLOWLIST 或改用允许的地址。"
                )

            attachments = collect_attachments(
                arguments.attachments,
                cwd=context.cwd,
                max_total_bytes=attachment_limit(),
            )
            result = send(
                Email(
                    to=tuple(to),
                    cc=tuple(cc),
                    bcc=tuple(bcc),
                    subject=arguments.subject,
                    body=arguments.body,
                    attachments=tuple(attachments),
                ),
                load_smtp_settings(),
            )
        except MailError as exc:
            return ToolResult(output=str(exc), is_error=True)

        return ToolResult(
            output=json.dumps(result, ensure_ascii=False, indent=2),
            metadata={"sent": True, "to": result["to"], "attachments": result["attachments"]},
        )
