"""High-level, provider-independent mail APIs."""

from .core import (
    MAIL_BUILTINS, MailAddressValue, MailMessageValue, MailSendResultValue,
    MailSenderValue, MailTransportResponse,
)
from .transports import send_transport

__all__ = [
    "MAIL_BUILTINS", "MailAddressValue", "MailMessageValue", "MailSendResultValue",
    "MailSenderValue", "MailTransportResponse", "send_transport",
]
