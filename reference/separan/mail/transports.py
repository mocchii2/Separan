"""Built-in SMTP and optional Amazon SES mail transports."""

import smtplib
import ssl

from .core import MailTransportResponse


class MailTransportError(Exception):
    def __init__(self, category, message):
        super().__init__(message); self.category = category


def _smtp(request):
    sender = request["sender"]; context = ssl.create_default_context()
    connection = None
    try:
        if sender.security == "tls":
            connection = smtplib.SMTP_SSL(sender.host, sender.port, timeout=sender.timeout_seconds, context=context)
        else:
            connection = smtplib.SMTP(sender.host, sender.port, timeout=sender.timeout_seconds)
            connection.ehlo(); connection.starttls(context=context); connection.ehlo()
        if sender.username is not None:
            try: password = sender.password.value.decode("utf-8")
            except UnicodeDecodeError: raise MailTransportError("mail_authentication_error", "SMTP password secret must be UTF-8 text.")
            connection.login(sender.username, password)
        recipients = request["to"] + request["cc"] + request["bcc"]
        refused = connection.sendmail(request["from"], recipients, request["raw"])
        if refused: raise MailTransportError("mail_send_error", f"SMTP refused {len(refused)} recipient(s); partial delivery may have occurred.")
        return MailTransportResponse(request["message_id"], len(recipients))
    except MailTransportError: raise
    except smtplib.SMTPAuthenticationError: raise MailTransportError("mail_authentication_error", "SMTP authentication failed.")
    except (smtplib.SMTPConnectError, TimeoutError, OSError, ssl.SSLError) as exc: raise MailTransportError("mail_connection_error", f"SMTP connection failed: {exc}")
    except smtplib.SMTPException as exc: raise MailTransportError("mail_send_error", f"SMTP rejected the message: {exc}")
    finally:
        if connection is not None:
            try: connection.quit()
            except Exception:
                try: connection.close()
                except Exception: pass


def _ses(request):
    try: import boto3
    except ImportError: raise MailTransportError("mail_provider_error", 'Amazon SES provider is not installed. Install with: pip install "separan[ses]"')
    sender = request["sender"]
    recipients = request["to"] + request["cc"] + request["bcc"]
    try:
        from botocore.config import Config
        client = boto3.client("sesv2", region_name=sender.region, config=Config(connect_timeout=sender.timeout_seconds, read_timeout=sender.timeout_seconds, retries={"max_attempts": 3, "mode": "standard"}))
        destination = {name: values for name, values in (("ToAddresses", request["to"]), ("CcAddresses", request["cc"]), ("BccAddresses", request["bcc"])) if values}
        response = client.send_email(
            FromEmailAddress=request["from"],
            Destination=destination,
            Content={"Raw": {"Data": request["raw"]}},
        )
    except Exception as exc:
        lowered = str(exc).lower()
        category = "mail_authentication_error" if any(word in lowered for word in ("credential", "signature", "access denied", "not authorized")) else "mail_send_error"
        raise MailTransportError(category, f"Amazon SES send failed: {exc}")
    message_id = response.get("MessageId")
    if type(message_id) is not str or not message_id: raise MailTransportError("mail_send_error", "Amazon SES returned no MessageId.")
    return MailTransportResponse(message_id, len(recipients))


def send_transport(request):
    if request["sender"].provider == "smtp": return _smtp(request)
    if request["sender"].provider == "ses": return _ses(request)
    raise MailTransportError("mail_provider_error", "Unsupported mail provider.")
