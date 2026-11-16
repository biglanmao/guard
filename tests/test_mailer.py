"""mailer 邮箱发送模块测试（仅依赖标准库）。"""

from __future__ import annotations

import smtplib
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "guard-email"
if str(PLUGIN / "lib") not in sys.path:
    sys.path.insert(0, str(PLUGIN / "lib"))

from mailer import (  # noqa: E402
    Attachment,
    Email,
    MailError,
    SmtpSettings,
    attachment_limit,
    build_message,
    collect_attachments,
    default_config_path,
    load_smtp_settings,
    normalize_recipients,
    parse_allowlist,
    recipient_allowed,
    send,
    verify_connection,
)


class SmtpSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write_config(self, payload: str) -> Path:
        path = self.tmp / "mail.json"
        path.write_text(payload, encoding="utf-8")
        return path

    def load(self, env: dict[str, str], config: Path | None = None) -> SmtpSettings:
        path = config or self.write_config("{}")
        return load_smtp_settings(
            {"OPENHARNESS_GUARD_EMAIL_CONFIG": str(path), **env}
        )

    def test_defaults_and_sender_fallback(self) -> None:
        settings = self.load(
            {
                "OPENHARNESS_GUARD_SMTP_HOST": "smtp.example.com",
                "OPENHARNESS_GUARD_SMTP_USER": "bot@example.com",
                "OPENHARNESS_GUARD_SMTP_PASSWORD": "secret",
            }
        )
        self.assertEqual(settings.port, 587)
        self.assertEqual(settings.security, "starttls")
        self.assertEqual(settings.sender, "bot@example.com")
        self.assertEqual(settings.username, "bot@example.com")

    def test_ssl_default_port(self) -> None:
        settings = self.load(
            {
                "OPENHARNESS_GUARD_SMTP_HOST": "smtp.example.com",
                "OPENHARNESS_GUARD_SMTP_SECURITY": "ssl",
                "OPENHARNESS_GUARD_SMTP_FROM": "guard@example.com",
            }
        )
        self.assertEqual(settings.port, 465)
        self.assertEqual(settings.sender, "guard@example.com")

    def test_config_file_values(self) -> None:
        config = self.write_config(
            '{"host": "smtp.file", "port": 2525, "security": "none",'
            ' "username": "u", "password": "p", "from": "f@example.com"}'
        )
        settings = self.load({}, config)
        self.assertEqual(settings.host, "smtp.file")
        self.assertEqual(settings.port, 2525)
        self.assertEqual(settings.security, "none")
        self.assertEqual(settings.sender, "f@example.com")

    def test_environment_overrides_config(self) -> None:
        config = self.write_config('{"host": "smtp.file", "from": "f@example.com"}')
        settings = self.load({"OPENHARNESS_GUARD_SMTP_HOST": "smtp.env"}, config)
        self.assertEqual(settings.host, "smtp.env")

    def test_missing_host_raises(self) -> None:
        with self.assertRaises(MailError):
            self.load({})

    def test_username_without_password_raises(self) -> None:
        with self.assertRaises(MailError):
            self.load(
                {
                    "OPENHARNESS_GUARD_SMTP_HOST": "smtp.example.com",
                    "OPENHARNESS_GUARD_SMTP_USER": "bot@example.com",
                }
            )

    def test_invalid_security_raises(self) -> None:
        with self.assertRaises(MailError):
            self.load(
                {
                    "OPENHARNESS_GUARD_SMTP_HOST": "smtp.example.com",
                    "OPENHARNESS_GUARD_SMTP_SECURITY": "plain",
                    "OPENHARNESS_GUARD_SMTP_FROM": "guard@example.com",
                }
            )

    def test_missing_explicit_config_raises(self) -> None:
        with self.assertRaises(MailError):
            load_smtp_settings(
                {"OPENHARNESS_GUARD_EMAIL_CONFIG": str(self.tmp / "nope.json")}
            )

    def test_invalid_config_json_raises(self) -> None:
        config = self.write_config("{oops")
        with self.assertRaises(MailError):
            self.load({}, config)


class RecipientTest(unittest.TestCase):
    def test_normalize_and_dedupe(self) -> None:
        recipients = normalize_recipients(
            ["Alice <a@example.com>", "b@example.com,c@example.com", "a@example.com"]
        )
        self.assertEqual(recipients, ["a@example.com", "b@example.com", "c@example.com"])

    def test_invalid_address_raises(self) -> None:
        with self.assertRaises(MailError):
            normalize_recipients(["not-an-email"])

    def test_header_injection_rejected(self) -> None:
        with self.assertRaises(MailError):
            normalize_recipients(["a@example.com\nBcc: evil@example.com"])

    def test_allowlist(self) -> None:
        allowlist = parse_allowlist("a@example.com, @corp.com; b@other.com")
        self.assertEqual(allowlist, ["a@example.com", "@corp.com", "b@other.com"])
        self.assertTrue(recipient_allowed("a@example.com", allowlist))
        self.assertTrue(recipient_allowed("anyone@corp.com", allowlist))
        self.assertTrue(recipient_allowed("b@other.com", allowlist))
        self.assertFalse(recipient_allowed("c@other.com", allowlist))
        self.assertTrue(recipient_allowed("c@other.com", []))
        self.assertEqual(parse_allowlist(None), [])


class AttachmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_collect_relative_path(self) -> None:
        (self.tmp / "report.txt").write_text("hello", encoding="utf-8")
        attachments = collect_attachments(["report.txt"], cwd=self.tmp)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].filename, "report.txt")
        self.assertEqual(attachments[0].data, b"hello")
        self.assertEqual(attachments[0].maintype, "text")
        self.assertEqual(attachments[0].subtype, "plain")

    def test_missing_attachment_raises(self) -> None:
        with self.assertRaises(MailError):
            collect_attachments(["missing.txt"], cwd=self.tmp)

    def test_size_limit(self) -> None:
        (self.tmp / "big.bin").write_bytes(b"0123456789")
        with self.assertRaises(MailError):
            collect_attachments(["big.bin"], cwd=self.tmp, max_total_bytes=5)

    def test_attachment_limit(self) -> None:
        self.assertEqual(attachment_limit({"OPENHARNESS_GUARD_EMAIL_MAX_BYTES": "1024"}), 1024)
        self.assertEqual(attachment_limit({}), 20 * 1024 * 1024)
        self.assertEqual(attachment_limit({"OPENHARNESS_GUARD_EMAIL_MAX_BYTES": "x"}), 20 * 1024 * 1024)

    def test_default_config_path_follows_config_dir(self) -> None:
        self.assertEqual(
            default_config_path({}),
            Path.home() / ".openharness" / "guard-email.json",
        )
        self.assertEqual(
            default_config_path({"OPENHARNESS_CONFIG_DIR": "/tmp/oh-config"}),
            Path("/tmp/oh-config") / "guard-email.json",
        )


class MessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SmtpSettings(
            host="smtp.example.com",
            port=587,
            sender="guard@example.com",
            username="guard@example.com",
            password="secret",
        )

    def test_message_headers_and_attachment(self) -> None:
        email = Email(
            to=("a@example.com",),
            cc=("b@example.com",),
            bcc=("c@example.com",),
            subject="季度报告\n第二行",
            body="见附件",
            attachments=(Attachment("report.txt", b"hello", "text", "plain"),),
        )
        message = build_message(self.settings, email)
        self.assertEqual(message["From"], "guard@example.com")
        self.assertEqual(message["To"], "a@example.com")
        self.assertEqual(message["Cc"], "b@example.com")
        self.assertEqual(message["Subject"], "季度报告 第二行")
        self.assertNotIn("c@example.com", message.as_string())
        body_part = message.get_body(preferencelist=("plain",))
        self.assertIsNotNone(body_part)
        self.assertEqual(body_part.get_content().strip(), "见附件")
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "report.txt")
        self.assertEqual(attachments[0].get_payload(decode=True), b"hello")


class FakeSMTP:
    def __init__(self, settings: SmtpSettings, *, fail: bool = False) -> None:
        self.settings = settings
        self.fail = fail
        self.calls: list[str] = []
        self.sent: tuple | None = None

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(f"login:{username}")

    def send_message(self, message, from_addr=None, to_addrs=None) -> None:
        if self.fail:
            raise smtplib.SMTPServerDisconnected("boom")
        self.calls.append("send_message")
        self.sent = (message, from_addr, to_addrs)

    def quit(self) -> None:
        self.calls.append("quit")


class SendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SmtpSettings(
            host="smtp.example.com",
            port=587,
            sender="guard@example.com",
            username="guard@example.com",
            password="secret",
        )

    def email(self) -> Email:
        return Email(
            to=("a@example.com",),
            bcc=("hidden@example.com",),
            subject="测试",
            body="正文",
        )

    def test_send_starttls_and_login(self) -> None:
        fake = FakeSMTP(self.settings)
        result = send(self.email(), self.settings, smtp_factory=lambda _: fake)
        self.assertTrue(result["sent"])
        self.assertEqual(result["to"], ["a@example.com"])
        self.assertEqual(result["bcc_count"], 1)
        self.assertIn("starttls", fake.calls)
        self.assertIn("login:guard@example.com", fake.calls)
        self.assertEqual(fake.calls[-1], "quit")
        _, from_addr, to_addrs = fake.sent
        self.assertEqual(from_addr, "guard@example.com")
        self.assertEqual(to_addrs, ["a@example.com", "hidden@example.com"])

    def test_send_without_tls(self) -> None:
        settings = SmtpSettings(host="h", port=25, sender="g@example.com", security="none")
        fake = FakeSMTP(settings)
        send(self.email(), settings, smtp_factory=lambda _: fake)
        self.assertNotIn("starttls", fake.calls)

    def test_send_failure_raises_mail_error(self) -> None:
        fake = FakeSMTP(self.settings, fail=True)
        with self.assertRaises(MailError):
            send(self.email(), self.settings, smtp_factory=lambda _: fake)
        self.assertEqual(fake.calls[-1], "quit")

    def test_connection_error_raises_mail_error(self) -> None:
        def broken_factory(_settings):
            raise OSError("connection refused")

        with self.assertRaises(MailError) as ctx:
            send(self.email(), self.settings, smtp_factory=broken_factory)
        self.assertIn("无法连接", str(ctx.exception))

    def test_verify_connection_logs_in(self) -> None:
        fake = FakeSMTP(self.settings)
        verify_connection(self.settings, smtp_factory=lambda _: fake)
        self.assertIn("starttls", fake.calls)
        self.assertIn("login:guard@example.com", fake.calls)
        self.assertEqual(fake.calls[-1], "quit")

    def test_verify_connection_login_failure(self) -> None:
        class FailingLogin(FakeSMTP):
            def login(self, username: str, password: str) -> None:
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        with self.assertRaises(MailError):
            verify_connection(self.settings, smtp_factory=lambda _: FailingLogin(self.settings))

    def test_empty_recipients_raise(self) -> None:
        with self.assertRaises(MailError):
            send(Email(to=(), subject="x"), self.settings, smtp_factory=lambda _: FakeSMTP(self.settings))


if __name__ == "__main__":
    unittest.main()
