# mail — 読めるmessageと明示的transport

状態: **v0.2.0-alpha.4で送信previewを実装済み。**

Separanのmailは用途で分けます。programはprovider非依存messageを組み立て、senderを明示的に
選択します。MIME boundary、header encoding、content-transfer encoding、SMTP session、
AWS request署名は言語level APIとして公開しません。

## message作成

```separan
function:send_alert
@notification
@mail

message = mail_create_message()
mail_set_sender(message, mail_address("monitor@example.com", display_name = "監視"))
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

実装済みmessage関数:

- `mail_address(text[, display_name])`
- `mail_create_message()`
- `mail_set_sender(message, address)`
- `mail_add_recipient(message, address)`
- `mail_add_cc_recipient(message, address)`
- `mail_add_bcc_recipient(message, address)`
- `mail_set_subject(message, subject)`
- `mail_set_text_body(message, text)`
- `mail_set_html_body(message, html)`

address引数はASCII address stringまたは検証済み`mail_address`です。表示名、subject、body、
filenameはUTF-8です。address自体は、SMTPUTF8を実装しないSES等でもportableになるよう、
意図的に厳しいASCII addr-spec subsetに限定します。header改行はMIME構築前に拒否します。

sender、subject、各bodyはそれぞれ1回だけ設定できます。recipientはTo／Cc／Bcc全体で一意、
送信時にはsender、1件以上のrecipient、明示subject、textまたはHTML bodyが必須です。

## 添付

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

`mail_add_attachment`と`mail_add_inline_attachment`はfile capability内の相対pathを読みます。
bytes版はstringをbinaryへ暗黙変換しません。inline添付にはHTML bodyと安全なContent-IDが必須です。
初期のprovider共通上限はraw添付合計7,000,000 bytes、serialize済みMIME 10,000,000 bytesで、
host capabilityはさらに小さい上限を設定できます。

runtimeは標準MIME object modelとSMTP wire policyを使います。Bcc addressはenvelope送信先だけに
含め、MIME headerには絶対に書きません。

## sender provider

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

`security`は`starttls`またはimplicit TLSの`tls`だけです。平文SMTPと証明書検証の無効化は
提供しません。usernameとpasswordは同時指定し、passwordはsecret限定です。各sendがSMTP
sessionを所有して閉じます。低level connect／authenticate／close handleは意図的に作りません。

Amazon SES sender:

```separan
mailer = mail_create_sender(
    provider = "ses",
    region = "ap-northeast-1"
)
```

SESはAWS SDKのcredential chainとraw message APIを使うので、SMTPと全く同じMIME messageを
送れます。optional adapterは`pip install "separan[ses]"`で導入します。Separan自身でAWS署名を
実装しません。

`mail_send_message(mailer, message)`は`provider`、`message_id`、`accepted_recipients`を持つ
`mail_send_result`を返します。一部recipientだけ成功する状態は黙って成功させずerrorです。

## capabilityとsecret

送信には`network`に加えて独立した`send_mail` host capabilityが必要です。hostは接続host、port、
envelope sender、recipient、recipient数、message bytes、timeoutを個別に制限できます。
private network宛てには既存の明示的private-network許可も必要です。

reference CLIはdefaultでmail capabilityを一切付与しません。正確なtransport hostを
`--allow-mail-host`で許可し、必要なら`--allow-mail-port`、`--allow-mail-sender`、
`--allow-mail-recipient`でさらに絞ります。private SMTP hostには
`--allow-private-mail-network`も必要です。

`secret_from_environment(name)`はenvironment capabilityとallowlistを通してsecretを返します。
SMTP credentialは標準表示ですべてredactし、MIME出力にも含めません。

診断は`E930`～`E939`です。address、attachment、provider、connection、authentication、sendの
各errorは、label付き`try`／`catch`で`mail_error`の子として扱います。

IMAP受信、mailbox変更、template、DKIM署名、長寿命SMTP sessionは別の将来設計です。
MIME構築primitiveは今後も内部に留めます。
