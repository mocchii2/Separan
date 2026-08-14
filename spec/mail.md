# Mail — Readable Messages and Explicit Transports

Status: **experimental sending preview implemented in v0.2.0-alpha.4**.

Separan exposes mail by purpose: programs compose a provider-independent
message and explicitly select a sender. MIME boundaries, header encoding,
content-transfer encoding, SMTP sessions, and AWS request signing are not
language-level APIs.

## Message composition

```separan
function:send_alert
@notification
@mail

message = mail_create_message()
mail_set_sender(message, mail_address("monitor@example.com", display_name = "Monitor"))
mail_add_recipient(message, "operator@example.com")
mail_set_subject(message, "[CRITICAL] WEB01")
mail_set_text_body(message, "CPU usage exceeded 95%.")

mailer = mail_create_sender(
    provider = "smtp",
    host = "smtp.example.com",
    security = "starttls",
    username = "monitor",
    password = secret_from_environment("SMTP_PASSWORD")
)

result = mail_send_message(mailer, message)
print result.message_id
end_function:send_alert
```

Implemented message functions:

- `mail_address(text[, display_name])`
- `mail_create_message()`
- `mail_set_sender(message, address)`
- `mail_add_recipient(message, address)`
- `mail_add_cc_recipient(message, address)`
- `mail_add_bcc_recipient(message, address)`
- `mail_set_subject(message, subject)`
- `mail_set_text_body(message, text)`
- `mail_set_html_body(message, html)`

An address argument may be an ASCII address string or a validated
`mail_address`. Display names, subjects, bodies, and filenames are UTF-8. The
address itself uses a deliberately strict ASCII addr-spec subset so behavior is
portable to providers such as SES that do not implement SMTPUTF8. Header line
breaks are rejected before MIME construction.

Each sender, subject, and body kind may be set only once. Recipient addresses
must be unique across To, Cc, and Bcc. Sending requires a sender, at least one
recipient, an explicitly set subject, and at least one text or HTML body.

## Attachments

```separan
mail_add_attachment(message, "reports/status.csv", content_type = "text/csv")

mail_add_attachment_bytes(
    message,
    "snapshot.bin",
    data,
    "application/octet-stream"
)

mail_add_inline_attachment_bytes(
    message,
    "graph.png",
    graph,
    "image/png",
    "cpu_graph"
)
```

`mail_add_attachment` and `mail_add_inline_attachment` read a relative path
through the file capability. Bytes variants never reinterpret a string as
binary. Inline attachments require an HTML body and a safe explicit Content-ID.
The initial cross-provider limits are 7,000,000 raw attachment bytes and
10,000,000 serialized MIME bytes; a stricter host capability can lower them.

The runtime uses the standard MIME object model and SMTP wire policy. Bcc
addresses are envelope destinations only and are never written into the MIME
headers.

## Sender providers

SMTP sender:

```separan
mailer = mail_create_sender(
    provider = "smtp",
    host = "smtp.example.com",
    port = 587,
    security = "starttls",
    username = "monitor",
    password = secret_from_environment("SMTP_PASSWORD"),
    timeout = duration("30s")
)
```

`security` is either `starttls` or `tls` (implicit TLS). Plaintext SMTP and
certificate-verification bypasses are not exposed. Username and password must
appear together, and password must be `secret`. Each send owns and closes its
SMTP session; low-level connect/authenticate/close handles are intentionally
absent.

Amazon SES sender:

```separan
mailer = mail_create_sender(
    provider = "ses",
    region = "ap-northeast-1"
)
```

SES uses the AWS SDK credential chain and the raw-message API so exactly the
same MIME message works with SMTP. Install the optional adapter with
`pip install "separan[ses]"`. Separan never implements AWS request signing
itself.

`mail_send_message(mailer, message)` returns `mail_send_result` with `provider`,
`message_id`, and `accepted_recipients`. Partial recipient acceptance is an
error because silent partial success is unsafe.

## Capabilities and secrets

Sending requires both `network` and the separate `send_mail` host capability.
The host can independently restrict destination hosts, ports, envelope sender
addresses, recipient addresses, recipient count, message bytes, and timeout.
Private network destinations require the existing explicit private-network
permission.

The reference CLI grants no mail capability by default. Enable an exact
transport host with `--allow-mail-host`, and optionally narrow it with
`--allow-mail-port`, `--allow-mail-sender`, and `--allow-mail-recipient`.
Private SMTP hosts additionally require `--allow-private-mail-network`.

`secret_from_environment(name)` returns `secret` through the environment
capability and its allowlist. SMTP credentials are redacted in all standard
display paths and are never included in MIME output.

Diagnostics use `E930`–`E939`. Address, attachment, provider, connection,
authentication, and send errors are children of `mail_error` for labeled
`try`/`catch` handling.

IMAP receiving, mailbox mutation, templates, DKIM signing, and long-lived SMTP
sessions are separate future designs. MIME construction primitives remain
internal.
