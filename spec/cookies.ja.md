# HTTP CookieとCookie Jar

状態: **実験的プレビュー実装あり。**

単発Cookieは`cookies = object`、継続通信は明示的な可変専用型`cookie_jar`を使います。

```separan
object:cookies
lang = "ja"
end_object:cookies
response = http_get(url, cookies = cookies)

jar = cookie_jar()
http_get(login_url, cookie_jar = jar)
response = http_get(data_url, cookie_jar = jar)
```

APIは`cookie_jar`、`cookie_get`、`cookie_set`、`cookie_remove`、`cookie_clear`、
`cookie_all`です。HTTP responseの`Set-Cookie`は自動保存され、今回受信した値は
`response.cookies`へ入ります。Cookie値は`secret`なので表示時にredactされます。
`Set-Cookie`は通常の`response.headers`から除外し、文字列として漏らしません。

Jarはname、value、domain、path、expires/Max-Age、secure、http_only、same_site、host-only
状態を保持します。送信時にdomain/path/expiry/secureを検証します。手動でdomainを省略した
Cookieは、最初に使ったrequest hostへhost-onlyでbindされます。明示cookiesはredirectで
別originへ送信されません。

Cookie Jarだけは通信stateを表すため意図的な可変型です。普通のobject/listを可変には
しません。平文保存APIは存在しません。永続化は次のsecure APIだけです。

```separan
cookie_save_secure(jar, "cookies.sepc")
jar = cookie_load_secure("cookies.sepc")

cookie_save_secure(jar, "portable.sepc", password = password)
cookie_save_secure(jar, "external.sepc", key = secret_get("cookie_store_key"))
```

version 1 containerは`SEPARAN-COOKIE-STORE` magic、version、protection mode、salt、96bit
nonce、AES-256-GCM ciphertext＋128bit tagを持ちます。header全体もAADとして認証します。
鍵をcontainer内へ保存しません。

- default OS-bound: host keystore adapterが同一user/device用32byte keyを提供。
- password-bound: Argon2id、64MiB、3 iterations、4 lanes、random 16byte saltで256bit key導出。
- external-key: `secret`から正確に32byteのkeyを受け取る。KMS/Vault adapterの境界。

algorithmやcipher modeをSeparan sourceから選択できません。wrong key、改ざん、mode不一致は
復号dataを一切返さずerrorです。診断範囲は`E880`～`E889`です。
