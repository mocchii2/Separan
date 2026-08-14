# 乱数 — 実験的API

状態: **実装済みプレビュー。v0.2でAPI安定化予定。**

Separanは、再現可能な疑似乱数と暗号学的に安全な乱数を分離します。関数名から
乱数源と結果の意味が分かります。すべてを背負う`random()`や、セキュア乱数用の
seed APIは存在しません。

## 再現可能な疑似乱数

| 関数 | 結果 |
|---|---|
| `random_seed(seed)` | 現在の処理系PRNGをリセットしnullを返す |
| `random_number()` | `0 <= x < 1`のnumber |
| `random_int(min, max)` | 両端を含む整数値number |
| `random_float(min, max)` | `min <= x < max`を満たすnumber |
| `random_bool()` | boolean |
| `random_pick(items)` | 空でないlistから1要素 |
| `random_shuffle(items)` | シャッフル済みの新しいlist |
| `random_sample(items, count)` | 重複なしで抽出した新しいlist |

`random_shuffle`と`random_sample`は入力を変更しません。sample数は0からlist長までの
整数です。空listからのpickはエラーです。

各Interpreterは独立したPRNGを持ちます。`random_seed`を呼ばない場合はOS entropyで
初期化します。seedは整数値numberだけを受け付け、下位64bitを使用します。
生成器は次のPCG-XSH-RR 32です。

```text
multiplier = 6364136223846793005
stream increment = 109
64-bit wrapping state
```

`random_number`は27bitと26bitの出力を53bit小数へ結合します。整数選択はmoduloでは
なく棄却法、shuffleは降順Fisher–Yatesです。同じseedが適合処理系間で同じ列を
生成するよう、これらの詳細を規範仕様とします。

通常乱数はテスト、ゲーム、シミュレーション、一般的な抽選向けです。パスワード、
トークン、鍵、nonceには使ってはいけません。

## セキュア乱数

| 関数 | 結果 |
|---|---|
| `secure_random_bytes(length)` | 正確に`length`バイトの`bytes` |
| `secure_random_number(min, max)` | 両端を含む安全な整数値乱数 |
| `secure_random_int(min, max)` | 両端を含む安全な整数値乱数 |
| `secure_random_string(length)` | 正確に`length`文字のURL-safe string |

セキュア関数はOSの暗号学的乱数源を利用します。決定的seed操作はなく、
`random_seed`の影響を受けません。`secure_random_string`の文字集合は次の64文字だけです。
`secure_random_number`を読みやすい正式名とし、`secure_random_int`はalpha互換aliasとして残します。

```text
ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-
```

セキュアbytes／string長は0から1,048,576までの整数値numberです。このリソース上限は
プレビューAPIの一部です。

## `bytes`型

`secure_random_bytes`は不変の専用`bytes`型を導入します。numberのlistではなく、
stringへの暗黙変換も行いません。`len(bytes)`はバイト数を返します。明示的な
`string(bytes)`と`print bytes`は、`0x`接頭辞付き小文字16進表現を使います。
bytesリテラルはまだ定義しません。

## 診断

| コード | 分類 |
|---|---|
| `E501` | 不正な乱数範囲 |
| `E502` | 空の乱数母集団 |
| `E503` | 不正なsample数 |
| `E504` | 不正なセキュア乱数長 |

引数型・引数数の失敗は共通の`E201`と`E207`を使います。通常・セキュア乱数の
関数名はすべて予約されます。

## 将来の関数

`random_normal(mean, stddev)`などの確率分布は将来へ送ります。将来の分布関数は
分布名を関数名へ含め、seed再現性を保証する場合はアルゴリズムを文書化します。

