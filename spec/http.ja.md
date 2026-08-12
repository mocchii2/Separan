# HTTP Client — v0.2設計

状態: **実験的プレビュー実装あり。** `http_get`、`http_request`、`http_profile`、
固定shape response、scheme／host／port／private network／size／timeout capabilityを
利用できます。永続session、cookie、streaming、browser automationは含みません。

> HTTP取得とブラウザ自動化を混同しない。

Separanは、text中心の簡易APIと詳細response APIを分離します。JavaScript実行、DOM、
navigator、browser cookie、viewport、browser fingerprintは将来の`browser_*` moduleに
属し、`http_*`関数から暗黙に提供しません。

## 簡易API

```separan
html = http_get("https://example.com")
```

`http_get`はGETを行い、decode済みresponse bodyをstringで返します。成功以外のstatus、
未対応encoding、不正text、body上限、redirect違反、TLS失敗、timeout、network失敗は
catch可能な`http_error` subtypeです。error pageを成功として返しません。

詳細optionはnamed argumentを使います。

```separan
html = http_get(
    "https://example.com",
    profile = http_profile("desktop", language = "ja-JP"),
    timeout = duration("10s"),
    headers = {"X-Request-ID": "example"}
)
```

duration、boolean、objectの並び替えで意味が変わらないよう、optionはnamed argument必須です。
positional argumentを先に置き、名前は一意、未知の名前はparser errorにします。

## 詳細API

```separan
response = http_request(
    "https://example.com/api",
    method = "GET",
    timeout = duration("10s")
)

print response.status
print response.url
print response.text
print response.headers
```

`http_request`は汎用objectではなく、不変の`http_response`値を返します。

| field | 型 | 意味 |
|---|---|---|
| `status` | number | 整数HTTP status |
| `url` | string | redirect後の最終URL |
| `headers` | `object` | 正規化済みresponse header。任意keyはobject key APIでaccess |
| `bytes` | bytes | transfer decode後のraw body |
| `text` | stringまたはnull | decode成功時のtext |
| `encoding` | stringまたはnull | 選択された文字encoding |
| `redirects` | list[string] | 初期URLを除くredirect URL列 |

member accessは`http_response`など固定shape値に導入します。任意header keyは
`object_get(response.headers, "content-type")`を使います。

`http_request`は4xx／5xxだけではthrowせずstatusを検査できます。`http_get`は
`200 <= status < 300`を要求します。この違いは関数名から分かります。

## request optionとdefault

| option | default | 規則 |
|---|---|---|
| `method` | `"GET"` | 大文字の`GET`、`HEAD`、`POST`、`PUT`、`PATCH`、`DELETE` |
| `timeout` | `duration("30s")` | 正のduration、最大`5m` |
| `redirect` | true | boolean |
| `max_redirects` | 10 | 整数`0..20` |
| `encoding` | `"auto"` | `auto`、`utf-8`、または明示対応encoding |
| `profile` | `http_profile("separan")` | 明示的`http_profile`値 |
| `headers` | 空object | string-to-string object |
| `body` | null | string、bytes、null |
| `max_bytes` | 10,485,760 | decompress後の整数`0..67,108,864` |

methodとbodyの組み合わせは厳密です。初期APIでは`GET`と`HEAD`はbodyを拒否します。
`HEAD`のbytesは空でtextはnullです。暗黙JSON／form変換は行いません。将来helperは
`http_post_json`のようにserializationを名前へ含めます。

header名と値はcontrol文字・改行を拒否します。callerは`Host`、`Content-Length`、
`Transfer-Encoding`、`Connection`、proxy認証headerを設定できません。

## text decode

`encoding = "auto"`は決定的な順序です。

1. response `Content-Type`の有効かつ対応済み`charset`
2. それ以外はUTF-8

locale依存fallbackや不正byteの黙った置換は行いません。不正byteは
`http_decode_error`です。BOM規則と対応encoding registryは実装前にversion化します。
binary利用者は`http_get`ではなく`response.bytes`を使います。

圧縮responseを受け付けても、decompression bomb防止の`max_bytes`は展開後bodyへ
適用します。

## HTTP profile

```separan
profile = http_profile(
    "desktop",
    language = "ja-JP",
    user_agent = "ExampleClient/1.0"
)
```

`http_profile`はHTTP header用の不変設定です。初期fieldは次です。

```text
name
user_agent
accept
accept_language
accept_encoding
```

built-in名は`separan`、`desktop`、`mobile`です。正確なheader値はruntime release単位で
version化し、`http_profile_headers(profile)`で検査可能にします。

本物の互換browser transportがない限り、profileはChrome、Firefox、Safari、Windows、
Android等のemulationを名乗りません。Chrome風User-Agentだけ送ってもTLS fingerprint、
client hints、cookie、JavaScript環境は再現できません。そのため`desktop_chrome`等は
将来browser subsystem用に予約し、HTTP clientでは提供しません。

`os`、`screen_width`、`screen_height`はHTTP profile fieldではありません。通常HTTPは
screen寸法を送信しません。これらは将来`browser_open`で使う`browser_profile`に属し、
HTTP clientが独自headerを捏造してはいけません。`Sec-CH-UA*`も一貫したbrowser実装が
できるまでは送信しません。

defaultの`separan` profileは正直に自身を識別します。

```text
User-Agent: Separan/<runtime-version>
Accept: text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8
Accept-Language: en
Accept-Encoding: gzip, deflate
```

system languageはrequestを環境依存にするため暗黙利用しません。callerが明示します。

## network capabilityとSSRF防止

CLIまたはembedding hostが`network_capability`を許可しない限りHTTPは無効です。
capabilityは次を定義します。

- 許可scheme（defaultは`https`。`http`は明示許可時のみ）
- 許可host名またはsuffix
- 許可port
- loopback、private、link-local、multicast、reserved IPへの到達可否
- request／response最大size
- 任意のrequest数・合計時間budget

DNS結果を接続前にcapabilityと照合します。全redirect先も再度parse・resolve・検査します。
public URLから`127.0.0.1`、metadata endpoint、private addressへのredirectは明示許可が
なければ拒否します。URL user-infoは禁止、fragmentは送信せず、schemeはHTTP(S)のみです。

TLS証明書とhost名検証は必須で、初期APIに`verify = false`はありません。proxyと
environment proxy variableもhost capabilityが明示許可しない限り無効です。

## redirectと機密header

- redirect loopはエラー。
- `max_redirects`は追従回数。
- `301`／`302`／`303`は文書化したpolicyでPOSTをGETへ変更可能。
- `307`／`308`はmethodとbodyを維持。
- origin変更時は`Authorization`、`Cookie`等のcredential headerを除去。
- HTTPSからHTTPへのdowngradeはcapabilityがdowngradeと宛先の両方を許可しない限り拒否。

初期clientは永続cookie jarを持たず、各callは独立です。将来の`http_session`はcookieと
connection stateを明示します。

## error階層

```text
runtime_error
└─ http_error
   ├─ http_timeout_error
   ├─ http_dns_error
   ├─ http_tls_error
   ├─ http_redirect_error
   ├─ http_status_error       （http_getのみ）
   ├─ http_decode_error
   ├─ http_limit_error
   └─ permission_error
```

計画診断は`E780`～`E799`です。診断ではURL user-info、authorization、cookie等をredact
します。method、sanitized URL、判明時の経過duration、関連redirect chainを含めます。

## browserとの境界

将来のbrowser automationは別名・別型から開始します。

```separan
profile = browser_profile(
    browser = "chromium",
    os = "windows",
    screen_width = 1920,
    screen_height = 1080,
    language = "ja-JP"
)
page = browser_open("https://example.com", profile = profile)
```

browser subsystemはJavaScript、DOM、cookie、viewport、navigatorを扱えますが、本物の
browser engineが必要です。`http_get`／`http_request`へ暗黙に追加しません。

## 実装順序

1. named argumentと非破壊object API
2. catch可能runtime error値とnetwork capability注入
3. URL parser、redirect policy、body上限、注入可能transport
4. `http_response`、`http_profile`、fake transportによる決定的test
5. real HTTPS adapterとlocal controlled serverでの適合test
6. 後続の別moduleとしてbrowser subsystem

適合testはpublic internet serviceへ依存してはいけません。
