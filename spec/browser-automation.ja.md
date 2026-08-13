# Browser automation境界 v0.4

状態: **adapter境界を実装済み。engine連携は未同梱**。

Browser automationは`http_get`／`http_request`とは別subsystemです。JavaScript、DOM、
viewport、navigator、browser cookieの挙動には本物のbrowser engineが必要です。
reference packageはadapter契約として`BrowserProfile`、`BrowserPage`、`BrowserAdapter`、
`browser_open`を定義しました。HTTP fallbackがbrowserを装うことは禁止します。

最初のadapter engine名は`chromium`、`firefox`、`webkit`に固定します。core interpreterへ
engine依存は追加しません。adapterなしで境界を呼ぶと、明示的な
`BrowserAutomationUnavailable`になります。

将来のSeparanソースAPIは実験段階で、capability必須にします。Python境界を先に置くことで、
HTTP clientへ結合せずにengine adapterを開発・testできます。
