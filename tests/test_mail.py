import sys
import unittest
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.capabilities import RuntimeCapabilities
from separan.auth import SecretValue
from separan.cli import execute, main as cli_main
from separan.errors import SeparanError
from separan.mail import MailSenderValue, MailTransportResponse
from separan.mail.transports import MailTransportError, _smtp


class FakeMailTransport:
    def __init__(self, response=None, failure=None):
        self.requests = []; self.response = response; self.failure = failure

    def __call__(self, request):
        self.requests.append(request)
        if self.failure is not None: raise self.failure
        count = len(request["to"] + request["cc"] + request["bcc"])
        return self.response or MailTransportResponse("provider-message-id", count)


class MailTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "tests" / "fixtures" / "http_root"
        self.capability = replace(
            RuntimeCapabilities.local(self.root),
            network=True,
            send_mail=True,
            network_hosts=frozenset({"smtp.test", "email.ap-northeast-1.amazonaws.com"}),
            network_ports=frozenset({443, 587}),
            allowed_mail_senders=frozenset({"monitor@example.com"}),
            allowed_mail_recipients=frozenset({"operator@example.com", "manager@example.com", "audit@example.com"}),
        )

    def assert_error(self, source, code, **options):
        if "function:" not in source: source = "function:main\n" + source + "end_function:main\n"
        with self.assertRaises(SeparanError) as caught: execute(source, capabilities=options.pop("capabilities", self.capability), **options)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_smtp_message_mime_utf8_recipients_bcc_and_attachments(self):
        transport = FakeMailTransport()
        source = '''function:main
mailer = mail_create_sender(provider = "smtp", host = "smtp.test", port = 587, security = "starttls", username = "monitor", password = secret_from_environment("SMTP_PASSWORD"))
message = mail_create_message()
sender = mail_address("monitor@example.com", display_name = "監視システム")
mail_set_sender(message, sender)
mail_add_recipient(message, "operator@example.com")
mail_add_cc_recipient(message, "manager@example.com")
mail_add_bcc_recipient(message, "audit@example.com")
mail_set_subject(message, "[重大] WEB01")
mail_set_text_body(message, "CPU使用率が95%を超えました。")
mail_set_html_body(message, "<p>CPU使用率が<strong>95%</strong>を超えました。</p><img src='cid:graph'>")
mail_add_attachment(message, "public/data.txt", content_type = "text/plain")
mail_add_attachment_bytes(message, "状態.bin", hexadecimal_to_bytes("00FF"), "application/octet-stream")
mail_add_inline_attachment_bytes(message, "graph.png", hexadecimal_to_bytes("89504E47"), "image/png", "graph")
result = mail_send_message(mailer, message)
print result.provider
print result.accepted_recipients
print result
print mailer
end_function:main
'''
        output = execute(source, capabilities=self.capability, environment_variables={"SMTP_PASSWORD": "top-secret"}, mail_transport=transport)[1]
        self.assertEqual(output, "smtp\n3\nmail_send_result(provider=smtp, accepted=3)\nmail_sender(provider=smtp, credentials=[REDACTED])\n")
        request = transport.requests[0]
        self.assertEqual(request["bcc"], ["audit@example.com"])
        self.assertNotIn(b"top-secret", request["raw"])
        self.assertIn(b"\r\n", request["raw"])

        message = BytesParser(policy=policy.default).parsebytes(request["raw"])
        self.assertEqual(str(message["From"]), "監視システム <monitor@example.com>")
        self.assertEqual(str(message["Subject"]), "[重大] WEB01")
        self.assertEqual(str(message["To"]), "operator@example.com")
        self.assertEqual(str(message["Cc"]), "manager@example.com")
        self.assertIsNone(message["Bcc"])
        self.assertIn("CPU使用率", message.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("<strong>95%</strong>", message.get_body(preferencelist=("html",)).get_content())
        attachments = list(message.iter_attachments())
        self.assertEqual({part.get_filename() for part in attachments}, {"data.txt", "状態.bin"})
        inline = next(part for part in message.walk() if part.get("Content-ID") == "<graph>")
        self.assertEqual(inline.get_content_type(), "image/png")

    def test_ses_uses_same_message_and_explicit_provider(self):
        transport = FakeMailTransport(MailTransportResponse("ses-id", 1))
        source = '''function:main
mailer = mail_create_sender(provider = "ses", region = "ap-northeast-1")
message = mail_create_message()
mail_set_sender(message, "monitor@example.com")
mail_add_recipient(message, mail_address("operator@example.com"))
mail_set_subject(message, "alert")
mail_set_text_body(message, "body")
result = mail_send_message(mailer, message)
print result.provider
print result.message_id
end_function:main
'''
        self.assertEqual(execute(source, capabilities=self.capability, mail_transport=transport)[1], "ses\nses-id\n")
        self.assertEqual(transport.requests[0]["sender"].provider, "ses")

    def test_address_header_and_message_validation_are_strict(self):
        for value in ("invalid", "a@@example.com", "a@example..com", "日本@example.com", "a@example.com\\nBcc:evil@example.com"):
            with self.subTest(value=value): self.assert_error(f'print mail_address("{value}")\n', "E930")
        duplicate = '''message = mail_create_message()
mail_add_recipient(message, "operator@example.com")
mail_add_cc_recipient(message, "operator@example.com")
'''
        self.assert_error(duplicate, "E932")
        incomplete = '''mailer = mail_create_sender(provider = "smtp", host = "smtp.test")
message = mail_create_message()
mail_send_message(mailer, message)
'''
        self.assert_error(incomplete, "E933", mail_transport=FakeMailTransport())

    def test_sender_requires_encryption_and_secret_password(self):
        self.assert_error('print mail_create_sender(provider = "smtp", host = "smtp.test", security = "none")\n', "E934")
        self.assert_error('print mail_create_sender(provider = "smtp", host = "smtp.test", username = "u", password = "plain")\n', "E201")
        self.assert_error('print mail_create_sender(provider = "ses", region = "Tokyo")\n', "E934")
        self.assert_error('print mail_create_sender(provider = "unknown")\n', "E934")

    def test_attachment_paths_and_mime_types_are_capability_checked(self):
        self.assert_error('message = mail_create_message()\nmail_add_attachment(message, "../secret.txt")\n', "E721")
        self.assert_error('message = mail_create_message()\nmail_add_attachment(message, "missing.txt")\n', "E935")
        self.assert_error('message = mail_create_message()\nmail_add_attachment_bytes(message, "x.bin", hexadecimal_to_bytes("00"), "bad type")\n', "E935")
        self.assert_error('message = mail_create_message()\nmail_add_inline_attachment_bytes(message, "x.png", hexadecimal_to_bytes("00"), "image/png", "bad>id")\n', "E935")
        inline_without_html = '''mailer = mail_create_sender(provider = "smtp", host = "smtp.test")
message = mail_create_message()
mail_set_sender(message, "monitor@example.com")
mail_add_recipient(message, "operator@example.com")
mail_set_subject(message, "alert")
mail_set_text_body(message, "body")
mail_add_inline_attachment_bytes(message, "x.png", hexadecimal_to_bytes("00"), "image/png", "graph")
mail_send_message(mailer, message)
'''
        self.assert_error(inline_without_html, "E933", mail_transport=FakeMailTransport())

    def test_capabilities_deny_send_host_sender_and_recipient(self):
        source = '''mailer = mail_create_sender(provider = "smtp", host = "smtp.test")
message = mail_create_message()
mail_set_sender(message, "monitor@example.com")
mail_add_recipient(message, "operator@example.com")
mail_set_subject(message, "alert")
mail_set_text_body(message, "body")
mail_send_message(mailer, message)
'''
        denied = replace(self.capability, send_mail=False)
        self.assert_error(source, "E720", capabilities=denied, mail_transport=FakeMailTransport())
        bad_recipient = replace(self.capability, allowed_mail_recipients=frozenset({"someone@example.com"}))
        self.assert_error(source, "E720", capabilities=bad_recipient, mail_transport=FakeMailTransport())
        bad_host = replace(self.capability, network_hosts=frozenset({"other.test"}))
        self.assert_error(source, "E720", capabilities=bad_host, mail_transport=FakeMailTransport())

    def test_transport_failures_are_typed_and_partial_delivery_is_error(self):
        base = '''function:main
mailer = mail_create_sender(provider = "smtp", host = "smtp.test")
message = mail_create_message()
mail_set_sender(message, "monitor@example.com")
mail_add_recipient(message, "operator@example.com")
mail_set_subject(message, "alert")
mail_set_text_body(message, "body")
try :send
mail_send_message(mailer, message)
catch mail_error :send
print "mail failed"
endtry:send
end_function:main
'''
        failure = FakeMailTransport(failure=MailTransportError("mail_connection_error", "offline"))
        self.assertEqual(execute(base, capabilities=self.capability, mail_transport=failure)[1], "mail failed\n")
        partial = FakeMailTransport(MailTransportResponse("partial", 0))
        self.assert_error(base.replace('try :send\n', '').replace('catch mail_error :send\nprint "mail failed"\nendtry:send\n', ''), "E939", mail_transport=partial)

    def test_builtin_smtp_adapter_uses_starttls_login_and_closes(self):
        sender = MailSenderValue("smtp", "smtp.example.com", 587, "starttls", "monitor", SecretValue(b"password"), None, 30)
        request = {"sender": sender, "from": "monitor@example.com", "to": ["operator@example.com"], "cc": [], "bcc": [], "raw": b"Subject: test\r\n\r\nbody", "message_id": "<id@example.com>"}
        connection = Mock(); connection.sendmail.return_value = {}
        with patch("separan.mail.transports.smtplib.SMTP", return_value=connection):
            result = _smtp(request)
        self.assertEqual(result, MailTransportResponse("<id@example.com>", 1))
        self.assertEqual(connection.ehlo.call_count, 2)
        connection.starttls.assert_called_once()
        connection.login.assert_called_once_with("monitor", "password")
        connection.sendmail.assert_called_once_with("monitor@example.com", ["operator@example.com"], request["raw"])
        connection.quit.assert_called_once()

    def test_cli_mail_capability_is_explicit_and_allowlisted(self):
        script = ROOT / "examples" / "hello.sep"
        with patch("separan.cli.Interpreter") as interpreter:
            self.assertEqual(cli_main(["--allow-mail-host", "smtp.test", "--allow-mail-port", "587", "--allow-mail-sender", "monitor@example.com", "--allow-mail-recipient", "operator@example.com", str(script)]), 0)
        capability = interpreter.call_args.kwargs["capabilities"]
        self.assertTrue(capability.network); self.assertTrue(capability.send_mail)
        self.assertEqual(capability.network_hosts, frozenset({"smtp.test"}))
        self.assertEqual(capability.network_ports, frozenset({587}))
        self.assertEqual(capability.allowed_mail_senders, frozenset({"monitor@example.com"}))
        self.assertEqual(capability.allowed_mail_recipients, frozenset({"operator@example.com"}))
        with self.assertRaises(SystemExit): cli_main(["--allow-private-mail-network", str(script)])


if __name__ == "__main__": unittest.main()
