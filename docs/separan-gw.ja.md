# separan-gw

`separan-gw` は Separan Gateway Worker です。解析済みの Separan アプリケーションを常駐させ、`http_route` 宣言を通じて HTTP リクエストを処理します。

これは HTTP web server 自体ではなく FastCGI backend です。Apache の `mod_proxy_fcgi`、nginx の `fastcgi_pass` など FastCGI 対応 front-end を設定 listener に接続すると、Separan の route を実行できます。

## トランスポート

既定のトランスポートは、標準入出力を使う行指向 JSON です。

```console
separan-gw --source app.sep --stdio
```

入力行ごとに JSON リクエストを1件読み、出力行ごとに JSON レスポンスを1件返します。

リクエスト例:

```json
{"method":"GET","path":"/health"}
```

レスポンス例:

```json
{"body":"ok","cookies":[],"headers":{"Content-Type":"text/plain"},"status":200}
```

標準入出力の JSON トランスポートは supervisor やテストで利用できます。バイナリ標準入出力では FastCGI v1 responder も利用できます。

```console
separan-gw --source app.sep --fastcgi-stdio
```

CGI リクエストパラメーター、query、headers、body を HTTP dispatcher に渡し、CGI status/headers と route body を FastCGI STDOUT records で返します。設定では `transport = fastcgi-stdio` を指定します。1つの stream につき同時に処理するリクエストは1件です。

FastCGI listener は `transport` と `listen` で選びます。

- `fastcgi-unix` と `listen = unix:<path>` は POSIX Unix domain socket を bind します。
- `fastcgi-tcp` と `listen = tcp:<host>:<port>` は TCP socket を bind します。IPv6 address は `tcp:[::1]:9000` のように角括弧で囲みます。
- `fastcgi-pipe` と `listen = pipe:<name>` は Windows named pipe を作成します。

TCP listener と named-pipe listener は、既定では single-worker です。POSIX では Unix/TCP listener に prefork supervisor を利用できます。Windows では named pipe listener に process supervisor を利用でき、TCP listener は single-worker です。

Linux の release bundle は x86_64 と ARM64（`aarch64`）を別々に配布します。Gateway と CLI は共通の `make install` で install できます。architecture 非依存の source bundle では、対象 Linux の C compiler で両方を build/install できます。

バイナリは `--config <path>` を受け取ります。設定 parser は `source`、3種類の FastCGI listener transport、および下記 supervisor settings に対応します。不明な key や transport/listener の不正な組み合わせは拒否します。

## Gateway の役割

worker はアプリケーションのロード、route dispatch、route parameters、query values、headers、cookies、request bodies、response headers、response cookies、redirects、status codes を担当します。front-end adapter は protocol framing と connection lifecycle を担当します。

FastCGI parser は stdio、socket、named pipe で共通です。Windows TCP は single-worker という platform 制約があります。POSIX socket と Windows named pipe では process supervisor を利用できます。

各 worker は一度に1つの connection を処理します。POSIX supervisor は bind 済み listener を fork worker 間で共有します。Windows の named-pipe worker は同じ pipe name で各自の instance を作成します。

各 adapter は1 request に対して1 response の意味を維持し、Separan value を汎用 template data として再解釈してはいけません。

## Process model

推奨する deployment 名:

```text
separan-gw
separan-gw.service
separan-gw.conf
separan-gw.sock
```

Linux では gateway 設定を `/etc/separan-gw/separan-gw.conf` に置き、runtime socket を `/run/separan-gw/separan-gw.sock` に配置します。

systemd unit は `/etc/systemd/system/separan-gw.service` に配置します。Red Hat 系では service environment override は通常 `/etc/sysconfig/separan-gw`、Debian 系では `/etc/default/separan-gw` を使います。付属の systemd template は sysconfig file から worker config の path を読み込みます。

Linux の配置例:

```text
/etc/systemd/system/separan-gw.service
/etc/separan-gw/separan-gw.conf
/etc/sysconfig/separan-gw
/run/separan-gw/separan-gw.sock
```

systemd unit は `separan-gw --config` を起動します。config に supervisor settings があれば、組み込み POSIX process manager が worker を管理します。worker の出力は systemd journal に記録されます。packaging template は `reference/c/packaging/systemd/separan-gw.service` と `reference/c/packaging/sysconfig/separan-gw` にあります。

POSIX では parent がアプリケーションを読み込み、copy-on-write runtime state を持つ worker を fork します。Windows では各 named-pipe worker が設定されたアプリケーションを読み込みます。worker は復旧不能な transport error または recycle limit 到達で終了し、supervisor が補充します。

設定例で使う supervisor settings:

- `workers`: worker 数。1から256まで。
- `max_memory`: 正の byte 数。`K`、`M`、`G` suffix を付けられます。
- `max_requests`: worker ごとの正の request recycle 上限。
- `restart_grace`: drain の期限。`ms`、`s`、`m` で指定します。
- `restart_backoff`: 終了した worker を再起動するまでの固定待ち時間。`ms`、`s`、`m` で指定します。

supervisor settings は FastCGI listener と一緒に指定します。POSIX worker は SIGTERM を受けると処理中の request を終えてから終了します。grace 期限を超えても終了しない worker は kill されます。Windows named-pipe worker は CTRL_BREAK を受け、同じ期限を超えた場合は強制終了されます。POSIX では parent に SIGHUP を送ると worker pool を drain し、同じ process 内で再実行して config と application source を読み直します。付属 systemd unit は既定で `systemctl reload` action を定義していません。

Windows では `--service` で登録し、SCM stop/shutdown controls で worker を drain できます。service parameter-change control は pool を置き換え、worker が config と application を読み直します。実行中の Windows supervisor は worker 数と restart policy を保持するため、これらの設定変更には service 再起動が必要です。

管理者 terminal から Windows service を登録する例:

```console
sc.exe create separan-gw binPath= "\"C:\Program Files\Separan\separan-gw.exe\" --config \"C:\ProgramData\Separan\separan-gw.conf\" --service" start= auto
sc.exe start separan-gw
```

config/application files を更新した後、次の control で reload を要求します。

```console
sc.exe control separan-gw paramchange
```

service は config と app を読み取れ、設定された TCP port または named pipe にアクセスできる account で実行してください。

## nginx / Apache

nginx FastCGI 設定では Unix socket listener と POSIX worker pool を利用できます。

```nginx
location / {
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME /srv/app/app.sep;
    fastcgi_pass unix:/run/separan-gw/separan-gw.sock;
}
```

Apache では同等の `mod_proxy_fcgi` backend を利用できます。TCP の場合は `transport = fastcgi-tcp` と `listen = tcp:127.0.0.1:9000` を設定し、front-end FastCGI client をその address に接続します。