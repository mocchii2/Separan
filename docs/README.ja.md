<p align="center">
  <img src="../logo/separan_logo.png" alt="Separan" width="720">
</p>

# Separan

> **構造は推測するものではなく、名付けるもの。**
>
> **インデントと括弧に苦しめられた民を救う。**

[English](../README.md) | 日本語

## 30秒で実行

```console
git clone https://github.com/mocchii2/Separan.git && cd Separan
python -m pip install -e .
python -m separan examples/hello.sep
```

Python 3.10以降が必要です。

## 5分で試す

最初に、正しいラベル付きblockを実行します。

```separan
if true :check
print "ok"
endif:check
```

次に、意図的に壊したサンプルを実行します。

```console
python -m separan examples/label_mismatch.sep
```

このコードでは、開始側と終了側が別の構造名になっています。

```separan
if true :check
print "ok"
endif:wrong
```

Separanは構造上の間違いを指し、必要だった終了ラベルを具体的に示します。

```text
SEPARAN E104: Block label mismatch

Expected:
endif:check

Actual:
endif:wrong
```

構造をインデントや括弧の数から推測せず、名前を付けて検証する。これだけで
Separanがどんな言語なのかを5分以内に確認できます。

Separanは、人間・AI・開発ツールがブロックの終わりを推測せずに読める、
ラベル構造型スクリプト言語です。インデントは装飾にすぎません。
すべてのブロックは明示的な識別子を持ち、開始側と終了側が一致しなければ
構文エラーになります。

```separan
function:main
name = "Separan"

if name != null :name_exists
print "Hello, " + name
endif:name_exists

end_function:main
```

Separanは、よくある間違いが黙って成功することを防ぎます。

```separan
if user.active :active_user
print "active"
endif:admin_user
```

この場合は単なる`SyntaxError`ではなく、期待されたラベル、実際のラベル、
開始位置を含む診断を表示します。

## 30秒デモ

Separanでは、AIに編集を許可する構造そのものへ名前を付けられます。

```separan
if user.active :active_user
print "active user"
endif:active_user
```

行番号ではなく、構造名でAIへ指示します。

```text
AI instruction:
Modify only :active_user
```

現在のParserは開始・終了ラベルの一致をすでに検証します。将来のAI edit-scope
検証では、同じ構造識別子をdiff境界として利用します。

```text
Future Separan verification:
No other block was modified.
```

同じラベルが、人間向けの説明、Parserが検証する構造、機械検証可能な編集境界を
兼ねることがSeparanの中心的な狙いです。

## v0.1.0-alpha.1

現在のPythonリファレンス実装には、厳密なラベル検証、詳細なエラー診断、
型推論後の型固定、同一型リスト、関数、`main`自動実行、条件分岐、ループ、
コメント、AST表示、基本的なVS Code TextMate Grammarが含まれます。

標準ライブラリには、明示的型変換、Unicode文字列、同型list、不変bytes、
datetime／duration、再現可能乱数とsecure乱数、filesystem／process utility、
HTTP client／server preview、認証、Cookie、parameter bindingを使うSQLiteが
実験実装されています。暗黙変換は禁止したまま、組み込み関数でも引数の数と型を
厳密に診断します。

文字列加工には`trim`、`upper`、`lower`、`contains`、`starts_with`、
`ends_with`、`split`、`join`、`replace`、Unicodeコードポイント単位の
`substring`を利用できます。

```console
python -m pip install -e .
separan examples/hello.sep
separan --ast examples/if.sep
python -m unittest discover -s tests -v
```

Python 3.10以降が必要です。

## Separanが大切にすること

- Whitespace is decoration.
- Labels define structure.
- Structure should be named, not guessed.
- 間違いを注意力に任せず、構文・型・ラベル検証で早期に止める。
- AIによる変更範囲を、人間が読める構造名で指定できるようにする。

詳しくは[言語仕様](../spec/README.ja.md)、[設計思想](philosophy.ja.md)、
[AI連携](ai-integration.ja.md)、[ロードマップ](../ROADMAP.md)を参照してください。
[時間型仕様](../spec/temporal-types.ja.md)では、datetime、local datetime、
timezone、durationを別の型として定義しています。この時間型はリファレンス実装へ
実験的に先行実装されています。`separan --timezone-version`で使用中のtimezone
データベースを確認できます。

乱数は、seedで再現可能な`random_*`系と、OSの暗号学的乱数源を使う
`secure_random_*`系に分離しています。セキュアな生バイト列はnumber listではなく
専用の`bytes`型です。詳細は[乱数仕様](../spec/randomness.ja.md)を参照してください。

bytesはstringと完全分離した不変binary型です。text encoding、hex、Base64、slice、concatは
すべて明示関数で行います。詳細は[bytes仕様](../spec/bytes.ja.md)を参照してください。

認証では暗号の自作を避け、Basic／Bearer／API key、OAuth client credentials、HMAC、JWT、
password hashを高level APIとして提供します。host由来secretは自動redactされます。詳細は
[認証とsecret仕様](../spec/authentication.ja.md)を参照してください。

HTTP Cookieは単発objectと継続通信用Cookie Jarに分離しています。値はsecretとしてredactし、
domain／path／expiry／Secureを送信時に検証します。詳細は
[Cookie仕様](../spec/cookies.ja.md)を参照してください。

listは同型・0始まりで、追加、削除、slice、reverse、sortをすべて非破壊操作として
提供します。詳細は[list仕様](../spec/lists.ja.md)を参照してください。

`length(value)`と`is_empty(value)`はstring、list、bytesで共通です。文字列検索、
繰り返し、paddingはUnicodeコードポイント単位で、`index_of`／`last_index_of`の
不在結果は`-1`ではなくnullです。

`const name = value`は再代入不能bindingを作り、通常代入は可変のままです。
label付きobject／list data block、namespace付きimport、capability型I/O、明示的JSON変換、
label付きerror処理は、すべてリファレンス処理系で実験的に利用できます。詳細は
[module・data・I/O・error仕様](../spec/modules-data-errors.ja.md)を参照してください。

HTTPは簡易`http_get`と詳細`http_request`に分け、network capabilityで明示許可します。
JavaScript、DOM、screen size、navigatorは将来の`browser_open`へ分離します。詳細は
[HTTP設計](../spec/http.ja.md)を参照してください。
`http_get`／`http_request`と正直なHTTP profileはnetwork capability付きで
リファレンス処理系へ先行実装済みです。

外部commandはargvを直接渡す`exec`を標準とし、nonzero exitをerror化する
`exec_checked`、shell syntaxを解釈する別capabilityの`shell_exec`へ分離します。詳細は
[外部process実行設計](../spec/process-execution.ja.md)を参照してください。
`exec`、`exec_checked`、`shell_exec`、`command_exists`はprocess capability付きで
リファレンス処理系へ先行実装済みです。

regexはmatch／search／find／replace／splitを分離し、不在はnullまたは空list、不正patternは
`regex_error`にします。glob結果は必ずsortし、environment変更は現在processと子process
だけに限定します。command lineでは`script_path()`と`command_args()`を分離します。
詳細は[system utility設計](../spec/system-utilities.ja.md)を参照してください。
これらのAPIと名前付き関数引数はリファレンス処理系で実験的に利用できます。

label付きobject/list、member access、namespace付きimport、label付き
`try/catch/finally/throw`もリファレンス処理系へ先行実装済みです。

## 状態

Separanは現在 **v0.1.0-alpha.1** の実験的な処理系です。v1.0までは構文や
診断が変更される可能性があります。現段階では本番利用ではなく、評価と
フィードバックを目的としています。

Separanは[Apache License 2.0](../LICENSE)で提供されます。帰属情報は
[NOTICE](../NOTICE)を参照してください。

公式ブランド画像として、横長の[Separanロゴ](../logo/separan_logo.png)と
正方形の[Separanマーク](../logo/separan_mark.png)を原本のまま収録しています。
