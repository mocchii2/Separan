# HTTPサーバー・プレビュー

Separanのルートは匿名コールバックではなく、名前付き構造として宣言する。

```separan
http_route GET "/user/:id" :user_page
id = request_param("id")
return_http(status = 200, body = "user=" + id)
end_http_route:user_page

http_host(host = "127.0.0.1", port = 8080)
```

プレビュー版は `GET`、`HEAD`、`POST`、`PUT`、`PATCH`、`DELETE` に対応する。
`request_method`、`request_path`、`request_header`、`request_param`、
`request_query`、`request_body`、`request_cookie` で現在のリクエストを参照する。
`return_http` はレスポンスを確定し、`redirect_http` は明示的なリダイレクトを返し、
`http_set_cookie` はCookieを追加する。明示的な応答がないルートは204、未一致は404となる。

`http_host` は開発用の同期ホストであり、`host_http` capabilityが必須である。
bind可能なhostとportは個別に制限できる。リファレンス実装の通信非依存dispatcherを、
将来のLambda/API Gatewayおよび本番ホスト用adapter境界とする。

`http_static(url = "/static/", directory = "public")` はcapability rootからの相対directoryを
GET/HEADで配信する。URL prefixは `/` で始まり `/` で終わらなければならない。
directoryは `index.html` に解決し、一覧表示は行わない。URL decode、`..`、backslash、絶対path、
symlinkによるroot脱出、存在しないfileからcapability境界外を開示しない。明示routeをstaticより優先する。

Cookieの読取値は自動redactされる `secret` 型で返す。レスポンスCookieの名前、値、path、
SameSiteは検証される。このプレビューはJavaScriptを実行せず、本番用サーバーではない。
