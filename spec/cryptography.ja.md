# 暗号 — 安全な一本道と明示的な境界

状態: **v0.2.0-alpha.3で実験的previewを実装済み。**

Separanは、安全な用途別APIとprotocolに必要な少数のprimitiveを分離します。cipher modeや
algorithm名を自由文字列で選ばせません。MD5、SHA-1、DES、RC4、AES-ECB、認証なし暗号、
利用者指定nonceは意図的に標準APIへ入れません。

## digest、HMAC、encoding

```separan
digest = sha256_hash(data)
signature = sha256_hmac(key, data)

hex = bytes_to_hexadecimal(digest)
digest = hexadecimal_to_bytes(hex)

text = bytes_to_base64(data)
data = base64_to_bytes(text)
```

digestは`sha256_hash`、`sha512_hash`、`sha3_256_hash`、`sha3_512_hash`、HMACは
`sha256_hmac`と`sha512_hmac`を実装しています。戻り値は暗黙整形したstringではなく、
不変`bytes`です。既存の`hmac_sha256`、`hex_encode`／`hex_decode`、
`base64_encode`／`base64_decode`は互換aliasとして残します。

この明示的なcrypto境界ではstringをUTF-8で扱い、bytesとsecretも直接入力できます。
`constant_time_equal(left, right)`は値による途中終了を避けてsecret互換値を比較します。

## password保存

```separan
stored = password_hash(password)
ok = password_verify(candidate, stored)
```

新規hashはrandom 16-byte salt付きArgon2idのversion付きPHC stringです。現在の固定値は
memory 64 MiB、3 iterations、parallelism 4、出力32 bytesです。alpha版で生成済みの
旧Separan scrypt形式も`password_verify`だけは継続して検証できるため、upgradeで既存hashを
無効にしません。一般digest関数はpassword保存APIではありません。

## 認証付き暗号

既存の正確な32-byte keyを使う場合:

```separan
encrypted = encrypt_authenticated(key, plaintext)
plaintext = decrypt_authenticated(key, encrypted)
```

keyはsecretまたはbytesだけで、string keyは拒否します。方式はAES-256-GCMだけです。
encryptは毎回12-byte nonceを内部生成し、方式metadataとauthentication tagをまとめた
version付き不透明bytes containerを返します。headerもassociated dataとして認証します。
改ざんまたはkey違いは`crypto_authentication_error`となり、壊れた平文は返しません。

containerは元のplaintextがstring、bytes、secretのどれだったかを保持します。secretを
decryptしてもsecretのままなので、表示時には引き続きredactされます。

安全なkey storeがないportable用途にはpassword APIを使います。

```separan
encrypted = encrypt_with_password(password, plaintext)
plaintext = decrypt_with_password(password, encrypted)
```

saltとnonceを内部生成し、固定Argon2id profileからAES-256 keyを導出し、version付きparameterを
認証済みcontainerへ記録します。protocol連携用の
`derive_key_from_password(password, salt_bytes)`はsecretを返し、saltは16 bytes以上必須です。

`secure_random_number(minimum, maximum)`は両端を含む整数`secure_random_int`の読みやすい正式名です。
`secure_random_bytes(length)`も引き続き利用できます。secure乱数へseedは設定できません。

診断は`E890`～`E899`です。label付き`try`／`catch`では
`crypto_authentication_error`を`crypto_error`の子として扱います。
