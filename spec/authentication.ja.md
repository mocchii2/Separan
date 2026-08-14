# 認証とsecret — 安全な高level API

状態: **実験的プレビュー実装あり。**

Separan sourceで暗号algorithmを自作させず、用途が固定された標準primitiveだけを提供します。

- `secret_get(name)` → 自動redactされる`secret`
- `basic_auth(username, password)`
- `bearer_auth(token)`
- `api_key_auth(name, value, location = "header")`
- `oauth_client_credentials(token_url, client_id, client_secret[, scope])`
- `hmac_sha256(key, message)` → bytes
- `jwt_sign(claims, key, algorithm = "HS256")`
- `jwt_verify(token, key, algorithm = "HS256")`
- `password_hash(password)`／`password_verify(password, hash)`

一般的な暗号境界は[暗号仕様](cryptography.ja.md)へ分離しています。

`secret`はstring／bytesと別型です。print、object表示、OAuth token表示では
`[REDACTED]`となり、`string(secret)`は禁止です。hostがsecret providerと名前allowlistを
注入しない限り`secret_get`は失敗します。

JWTはalgorithm confusionを避けるためHS256だけを明示対応し、32byte未満のkeyを拒否します。
protected headerを固定検証し、signatureをconstant-time比較し、`exp`／`nbf`もruntime clockで
検証します。claimsにsecretやbytesは格納できません。

password hashはrandom 16byte salt付きArgon2idです。旧alpha版のscrypt保存形式もverify互換だけは
残します。普通のSHA-256をpassword保存APIとして提供しません。保存formatはversion markerを持ち、
不正formatのverifyはfalseです。

OAuth previewはclient credentialsだけです。form bodyとBasic client authenticationを使い、
access tokenをstringではなくsecretとして返します。authorization code、device flow、browser
login、refresh管理は別設計です。

診断は`E870`～`E879`で、`auth_error`の下に`secret_error`と`oauth_error`を置きます。
