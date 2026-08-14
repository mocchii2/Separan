"""Readable mail composition with MIME and transport details kept internal."""

from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
import ipaddress
import mimetypes
import re
import socket

from ..auth import SecretValue
from ..errors import error
from ..randomness import BytesValue
from ..system_utilities import UtilityFunction
from ..temporal import DurationValue


MAX_RECIPIENTS = 50
MAX_SUBJECT_LENGTH = 998
MAX_BODY_BYTES = 8_000_000
MAX_ATTACHMENT_BYTES = 7_000_000
SAFE_CONTENT_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$")
SAFE_REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z0-9-]+-[1-9][0-9]*$")
SAFE_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
SAFE_CONTENT_ID = re.compile(r"^[A-Za-z0-9._@+-]{1,255}$")


@dataclass(frozen=True)
class MailAddressValue:
    address: str
    display_name: str | None = None

    def header_value(self):
        local, domain = self.address.rsplit("@", 1)
        return Address(display_name=self.display_name or "", username=local, domain=domain)


@dataclass(frozen=True)
class MailAttachmentValue:
    filename: str
    content: bytes
    content_type: str
    inline: bool = False
    content_id: str | None = None


@dataclass
class MailMessageValue:
    sender: MailAddressValue | None = None
    to: list = field(default_factory=list)
    cc: list = field(default_factory=list)
    bcc: list = field(default_factory=list)
    subject: str | None = None
    text_body: str | None = None
    html_body: str | None = None
    attachments: list = field(default_factory=list)


@dataclass(frozen=True)
class MailSenderValue:
    provider: str
    host: str | None = None
    port: int | None = None
    security: str | None = None
    username: str | None = None
    password: SecretValue | None = None
    region: str | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class MailTransportResponse:
    message_id: str
    accepted_recipients: int


@dataclass(frozen=True)
class MailSendResultValue:
    provider: str
    message_id: str
    accepted_recipients: int


def _message(value, function, position, runtime):
    if not isinstance(value, MailMessageValue):
        runtime.type_error(position, "mail_message", runtime.type_name(value), f"{function}() requires a mail message.")
    return value


def _safe_text(value, field_name, position, runtime, allow_empty=True):
    if type(value) is not str:
        runtime.type_error(position, "string", runtime.type_name(value), f"Mail {field_name} must be a string.")
    if "\r" in value or "\n" in value or (not allow_empty and not value):
        raise error("E931", "mail_error", f"Mail {field_name} is empty or contains a header line break.", position, actual=field_name)
    return value


def _address_value(value, position, runtime, display_name=None):
    if isinstance(value, MailAddressValue):
        if display_name is not None: raise error("E931", "mail_error", "display_name cannot be supplied for an existing mail_address.", position)
        return value
    if type(value) is not str: runtime.type_error(position, "string or mail_address", runtime.type_name(value), "Mail address must be a string or mail_address.")
    text = value
    try:
        text.encode("ascii")
        if not text or "\r" in text or "\n" in text or text.count("@") != 1: raise ValueError
        local, domain = text.rsplit("@", 1)
        if not local or not domain or domain.startswith(".") or domain.endswith(".") or ".." in text: raise ValueError
        Address(addr_spec=text)
    except (UnicodeError, ValueError):
        raise error("E930", "mail_address_error", "Mail address must be one ASCII addr-spec without a display name.", position, actual=repr(text))
    if display_name is not None:
        display_name = _safe_text(display_name, "display name", position, runtime)
    return MailAddressValue(text, display_name)


def _mail_address(arguments, named, position, runtime):
    return _address_value(arguments[0], position, runtime, named.get("display_name"))


def _create_message(arguments, named, position, runtime): return MailMessageValue()


def _set_sender(arguments, named, position, runtime):
    message = _message(arguments[0], "mail_set_sender", position, runtime)
    if message.sender is not None: raise error("E932", "mail_error", "Mail sender is already set.", position)
    message.sender = _address_value(arguments[1], position, runtime); return None


def _add_recipient(kind):
    function = {"to": "mail_add_recipient", "cc": "mail_add_cc_recipient", "bcc": "mail_add_bcc_recipient"}[kind]
    def implementation(arguments, named, position, runtime):
        message = _message(arguments[0], function, position, runtime); address = _address_value(arguments[1], position, runtime)
        existing = {item.address.lower() for item in message.to + message.cc + message.bcc}
        if address.address.lower() in existing: raise error("E932", "mail_error", "Recipient address is already present in this message.", position, actual=address.address)
        if len(existing) >= MAX_RECIPIENTS: raise error("E936", "mail_error", f"A message cannot exceed {MAX_RECIPIENTS} recipients.", position)
        getattr(message, kind).append(address); return None
    return implementation


def _set_subject(arguments, named, position, runtime):
    message = _message(arguments[0], "mail_set_subject", position, runtime)
    if message.subject is not None: raise error("E932", "mail_error", "Mail subject is already set.", position)
    subject = _safe_text(arguments[1], "subject", position, runtime)
    if len(subject) > MAX_SUBJECT_LENGTH: raise error("E936", "mail_error", "Mail subject is too long.", position, expected=f"at most {MAX_SUBJECT_LENGTH} characters", actual=str(len(subject)))
    message.subject = subject; return None


def _set_body(kind):
    function, attribute = ("mail_set_text_body", "text_body") if kind == "text" else ("mail_set_html_body", "html_body")
    def implementation(arguments, named, position, runtime):
        message = _message(arguments[0], function, position, runtime)
        if getattr(message, attribute) is not None: raise error("E932", "mail_error", f"Mail {kind} body is already set.", position)
        body = arguments[1]
        if type(body) is not str: runtime.type_error(position, "string", runtime.type_name(body), f"{function}() body must be a string.")
        size = len(body.encode("utf-8"))
        if size > MAX_BODY_BYTES: raise error("E936", "mail_error", f"Mail {kind} body is too large.", position, expected=f"at most {MAX_BODY_BYTES} UTF-8 bytes", actual=str(size))
        setattr(message, attribute, body); return None
    return implementation


def _content_type(value, filename, position, runtime):
    if value is None: value = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if type(value) is not str: runtime.type_error(position, "MIME content type string", runtime.type_name(value), "Attachment content_type must be a string.")
    if not SAFE_CONTENT_TYPE.fullmatch(value): raise error("E935", "mail_attachment_error", "Attachment content_type must be a safe type/subtype value.", position, actual=repr(value))
    return value.lower()


def _filename(value, position, runtime):
    value = _safe_text(value, "attachment filename", position, runtime, allow_empty=False)
    if "/" in value or "\\" in value or value in (".", ".."):
        raise error("E935", "mail_attachment_error", "Attachment filename must be a base name without path separators.", position, actual=value)
    return value


def _add_attachment_value(message, filename, content, content_type, inline, content_id, position):
    if len(content) > MAX_ATTACHMENT_BYTES: raise error("E936", "mail_error", "Attachment exceeds the raw attachment limit.", position, expected=f"at most {MAX_ATTACHMENT_BYTES} bytes", actual=str(len(content)))
    if sum(len(item.content) for item in message.attachments) + len(content) > MAX_ATTACHMENT_BYTES:
        raise error("E936", "mail_error", "Combined attachments exceed the raw attachment limit.", position, expected=f"at most {MAX_ATTACHMENT_BYTES} bytes")
    message.attachments.append(MailAttachmentValue(filename, content, content_type, inline, content_id)); return None


def _attachment_from_path(inline=False):
    function = "mail_add_inline_attachment" if inline else "mail_add_attachment"
    def implementation(arguments, named, position, runtime):
        message = _message(arguments[0], function, position, runtime)
        path_text = arguments[1]; path = runtime.capabilities.path(path_text, function, position)
        runtime.capabilities.require(runtime.capabilities.read_files, "read mail attachment", position)
        if not path.is_file(): raise error("E935", "mail_attachment_error", "Attachment path is not a regular file.", position, actual=path_text)
        try: content = path.read_bytes()
        except OSError as exc: raise error("E935", "mail_attachment_error", str(exc), position, actual=path_text)
        content_id = None
        if inline:
            content_id = _safe_text(arguments[2], "inline content_id", position, runtime, allow_empty=False)
            if not SAFE_CONTENT_ID.fullmatch(content_id): raise error("E935", "mail_attachment_error", "Inline content_id contains unsupported characters.", position, actual=repr(content_id))
        return _add_attachment_value(message, _filename(path.name, position, runtime), content, _content_type(named.get("content_type"), path.name, position, runtime), inline, content_id, position)
    return implementation


def _attachment_from_bytes(inline=False):
    function = "mail_add_inline_attachment_bytes" if inline else "mail_add_attachment_bytes"
    def implementation(arguments, named, position, runtime):
        message = _message(arguments[0], function, position, runtime); filename = _filename(arguments[1], position, runtime)
        content = arguments[2]
        if not isinstance(content, BytesValue): runtime.type_error(position, "bytes", runtime.type_name(content), f"{function}() content must be bytes.")
        content_type = _content_type(arguments[3], filename, position, runtime)
        content_id = None
        if inline:
            content_id = _safe_text(arguments[4], "inline content_id", position, runtime, allow_empty=False)
            if not SAFE_CONTENT_ID.fullmatch(content_id): raise error("E935", "mail_attachment_error", "Inline content_id contains unsupported characters.", position, actual=repr(content_id))
        return _add_attachment_value(message, filename, content.value, content_type, inline, content_id, position)
    return implementation


def _duration(value, position, runtime):
    if not isinstance(value, DurationValue) or value.milliseconds <= 0 or value.milliseconds > runtime.capabilities.max_mail_timeout_ms:
        raise error("E934", "mail_provider_error", "Mail timeout must be a positive duration within the host limit.", position)
    return value.milliseconds / 1000


def _create_sender(arguments, named, position, runtime):
    provider = named.get("provider")
    if provider not in ("smtp", "ses"): raise error("E934", "mail_provider_error", "mail_create_sender() provider must be smtp or ses.", position, actual=repr(provider))
    timeout = _duration(named.get("timeout", DurationValue(30_000)), position, runtime)
    if provider == "smtp":
        host = named.get("host"); security = named.get("security", "starttls")
        if type(host) is not str or not SAFE_HOST.fullmatch(host):
            raise error("E934", "mail_provider_error", "SMTP host must be a safe non-empty hostname.", position, actual=repr(host))
        if security not in ("starttls", "tls"): raise error("E934", "mail_provider_error", "SMTP security must be starttls or tls; plaintext SMTP is not supported.", position, actual=repr(security))
        port = named.get("port", 587 if security == "starttls" else 465)
        if type(port) is not int or not 1 <= port <= 65535: raise error("E934", "mail_provider_error", "SMTP port must be an integer from 1 through 65535.", position, actual=repr(port))
        username, password = named.get("username"), named.get("password")
        if (username is None) != (password is None): raise error("E934", "mail_provider_error", "SMTP username and password must be supplied together.", position)
        if username is not None:
            _safe_text(username, "SMTP username", position, runtime, allow_empty=False)
            if not isinstance(password, SecretValue): runtime.type_error(position, "secret SMTP password", runtime.type_name(password), "SMTP password must be a redacted secret.")
        forbidden = ("region",)
        if any(name in named for name in forbidden): raise error("E934", "mail_provider_error", "SES options cannot be used with SMTP.", position)
        return MailSenderValue(provider, host, port, security, username, password, None, timeout)
    region = named.get("region")
    if type(region) is not str or not SAFE_REGION.fullmatch(region): raise error("E934", "mail_provider_error", "SES region must be an explicit AWS region such as ap-northeast-1.", position, actual=repr(region))
    if any(name in named for name in ("host", "port", "security", "username", "password")): raise error("E934", "mail_provider_error", "SMTP options cannot be used with SES.", position)
    return MailSenderValue(provider, region=region, timeout_seconds=timeout)


def _all_recipients(message): return message.to + message.cc + message.bcc


def _build_mime(message, position):
    if message.sender is None: raise error("E933", "mail_error", "Mail message requires exactly one sender.", position)
    recipients = _all_recipients(message)
    if not recipients: raise error("E933", "mail_error", "Mail message requires at least one recipient.", position)
    if message.subject is None: raise error("E933", "mail_error", "Mail message requires an explicitly set subject.", position)
    if message.text_body is None and message.html_body is None: raise error("E933", "mail_error", "Mail message requires a text or HTML body.", position)
    if any(item.inline for item in message.attachments) and message.html_body is None:
        raise error("E933", "mail_error", "Inline attachments require an HTML body.", position)
    result = EmailMessage(policy=SMTP)
    result["From"] = message.sender.header_value()
    if message.to: result["To"] = tuple(item.header_value() for item in message.to)
    if message.cc: result["Cc"] = tuple(item.header_value() for item in message.cc)
    result["Subject"] = message.subject
    result["Date"] = formatdate(localtime=False)
    result["Message-ID"] = make_msgid()
    if message.text_body is not None:
        result.set_content(message.text_body, subtype="plain", charset="utf-8")
        if message.html_body is not None: result.add_alternative(message.html_body, subtype="html", charset="utf-8")
    else: result.set_content(message.html_body, subtype="html", charset="utf-8")
    for item in (entry for entry in message.attachments if entry.inline):
        main, sub = item.content_type.split("/", 1)
        html_part = result.get_body(preferencelist=("html",))
        html_part.add_related(item.content, maintype=main, subtype=sub, cid=f"<{item.content_id}>", filename=item.filename, disposition="inline")
    for item in (entry for entry in message.attachments if not entry.inline):
        main, sub = item.content_type.split("/", 1)
        result.add_attachment(item.content, maintype=main, subtype=sub, filename=item.filename)
    return result


def _allowed(value, allowlist):
    return allowlist is None or value.lower() in {item.lower() for item in allowlist}


def _validate_network(sender, position, runtime):
    capability = runtime.capabilities
    host = sender.host if sender.provider == "smtp" else f"email.{sender.region}.amazonaws.com"
    port = sender.port if sender.provider == "smtp" else 443
    if capability.network_hosts is not None and not any(host.lower() == allowed.lower() or host.lower().endswith("." + allowed.lower()) for allowed in capability.network_hosts):
        raise error("E720", "Permission error", "Mail provider host is outside the network allowlist.", position, actual=host)
    if capability.network_ports is not None and port not in capability.network_ports:
        raise error("E720", "Permission error", "Mail provider port is outside the network allowlist.", position, actual=str(port))
    from .transports import send_transport
    if runtime.mail_transport is send_transport and not capability.allow_private_network:
        try: addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc: raise error("E937", "mail_connection_error", str(exc), position, actual=host)
        for address in addresses:
            if not ipaddress.ip_address(address).is_global: raise error("E720", "Permission error", "Mail network capability rejects a non-public destination.", position, actual=str(address))


def _send_message(arguments, named, position, runtime):
    sender, message = arguments
    if not isinstance(sender, MailSenderValue): runtime.type_error(position, "mail_sender", runtime.type_name(sender), "mail_send_message() first argument must come from mail_create_sender().")
    message = _message(message, "mail_send_message", position, runtime); capability = runtime.capabilities
    capability.require(capability.send_mail, "send mail", position); capability.require(capability.network, "access mail network", position)
    _validate_network(sender, position, runtime)
    mime = _build_mime(message, position); recipients = _all_recipients(message)
    if len(recipients) > capability.max_mail_recipients: raise error("E936", "mail_error", "Recipient count exceeds the host capability.", position, expected=f"at most {capability.max_mail_recipients}", actual=str(len(recipients)))
    if not _allowed(message.sender.address, capability.allowed_mail_senders): raise error("E720", "Permission error", "Mail sender is outside the host allowlist.", position, actual=message.sender.address)
    for recipient in recipients:
        if not _allowed(recipient.address, capability.allowed_mail_recipients): raise error("E720", "Permission error", "Mail recipient is outside the host allowlist.", position, actual=recipient.address)
    raw = mime.as_bytes(policy=SMTP)
    if len(raw) > capability.max_mail_message_bytes: raise error("E936", "mail_error", "Serialized MIME message exceeds the host capability.", position, expected=f"at most {capability.max_mail_message_bytes} bytes", actual=str(len(raw)))
    request = {"sender": sender, "from": message.sender.address, "to": [item.address for item in message.to], "cc": [item.address for item in message.cc], "bcc": [item.address for item in message.bcc], "raw": raw, "message_id": str(mime["Message-ID"])}
    try: response = runtime.mail_transport(request)
    except Exception as exc:
        category = getattr(exc, "category", "mail_send_error")
        code = {"mail_provider_error": "E934", "mail_connection_error": "E937", "mail_authentication_error": "E938", "mail_send_error": "E939"}.get(category, "E939")
        raise error(code, category if category.endswith("_error") else "mail_send_error", str(exc), position)
    if not isinstance(response, MailTransportResponse) or type(response.message_id) is not str or type(response.accepted_recipients) is not int:
        raise error("E939", "mail_send_error", "Mail transport returned an invalid result.", position)
    if response.accepted_recipients != len(recipients): raise error("E939", "mail_send_error", "Mail transport did not accept every recipient; partial delivery may have occurred.", position, expected=str(len(recipients)), actual=str(response.accepted_recipients))
    return MailSendResultValue(sender.provider, response.message_id, response.accepted_recipients)


SENDER_OPTIONS = ("provider", "host", "port", "security", "username", "password", "region", "timeout")
MAIL_BUILTINS = (
    UtilityFunction("mail_address", 1, 1, _mail_address, ("display_name",)),
    UtilityFunction("mail_create_message", 0, 0, _create_message),
    UtilityFunction("mail_set_sender", 2, 2, _set_sender),
    UtilityFunction("mail_add_recipient", 2, 2, _add_recipient("to")),
    UtilityFunction("mail_add_cc_recipient", 2, 2, _add_recipient("cc")),
    UtilityFunction("mail_add_bcc_recipient", 2, 2, _add_recipient("bcc")),
    UtilityFunction("mail_set_subject", 2, 2, _set_subject),
    UtilityFunction("mail_set_text_body", 2, 2, _set_body("text")),
    UtilityFunction("mail_set_html_body", 2, 2, _set_body("html")),
    UtilityFunction("mail_add_attachment", 2, 2, _attachment_from_path(), ("content_type",)),
    UtilityFunction("mail_add_attachment_bytes", 4, 4, _attachment_from_bytes()),
    UtilityFunction("mail_add_inline_attachment", 3, 3, _attachment_from_path(True), ("content_type",)),
    UtilityFunction("mail_add_inline_attachment_bytes", 5, 5, _attachment_from_bytes(True)),
    UtilityFunction("mail_create_sender", 0, 0, _create_sender, SENDER_OPTIONS),
    UtilityFunction("mail_send_message", 2, 2, _send_message),
)
