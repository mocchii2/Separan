# 時間型設計 — v0.2

状態: **v0.2の実験的プレビューとしてPythonリファレンス実装へ先行実装済み。
APIはまだ安定版ではありません。**

> 時間には、その意味を持たせる。

Separanでは、時刻の標準表現としてstringや単位のないnumberを使いません。
瞬間、壁時計上の日時、タイムゾーン、経過時間は異なる概念なので、異なる型です。

## 型と不変条件

### `datetime`

一意に決まる瞬間と、その表示に使うタイムゾーンまたは固定オフセットを持ちます。
表示される現地日時が異なっても、同じ瞬間を示すdatetimeが存在します。v0.2の
最低精度は1ミリ秒です。対応する暦年は`0001`から`9999`です。

### `local_datetime`

タイムゾーンを持たない暦日と壁時計時刻です。これは瞬間ではありません。
`datetime`との比較・減算・暗黙変換は禁止します。

### `timezone`

`Asia/Tokyo`、`America/New_York`、`UTC`などのIANAタイムゾーン識別子を
明示的に保持します。`+09:00`のような固定オフセットもtimezone値です。
IANAゾーンの挙動は処理系同梱のバージョン付きタイムゾーンデータベースに従い、
CLIはそのバージョンを表示できなければなりません。

### `duration`

ミリ秒精度の符号付き固定経過時間です。durationの1日は常に24時間です。
月と年は固定長ではないため含めません。

## 生成

```separan
instant = datetime("2026-08-13T01:30:00+09:00")
utc = datetime("2026-08-12T16:30:00Z")
wall = local_datetime("2026-08-13T01:30:00")
tokyo = timezone("Asia/Tokyo")
wait = duration("1h30m")
```

`datetime(string)`は次のRFC 3339限定形式だけを受け付けます。

```text
YYYY-MM-DDTHH:MM:SS[.fraction](Z|+HH:MM|-HH:MM)
```

- タイムゾーンオフセットは必須。
- `T`と`Z`は使う場合に大文字必須。
- 前後空白は禁止。
- 小数秒は1～3桁で、ミリ秒へ正規化。
- v0.2ではうるう秒（`:60`）を拒否。
- 存在しない日付や不正オフセットを補正せず拒否。
- 数値オフセットは`-14:00`から`+14:00`まで。14時間境界の分は`00`のみ。
  不明オフセットを意味する`-00:00`は拒否。

`local_datetime(string)`は同じ日付・時刻フィールドを使いますが、ゾーン接尾辞を
禁止します。空白ではなく`T`を使います。

```text
YYYY-MM-DDTHH:MM:SS[.fraction]
```

`timezone(string)`は利用可能な正規IANA識別子、`UTC`、または固定
`+HH:MM`／`-HH:MM`を受け付けます。未知の識別子はエラーです。ゾーン名は
大文字小文字を区別し、別名は可能な限り処理系の正規識別子へ統一します。

## ローカル日時の解決

壁時計日時から瞬間への変換は常に明示します。

```separan
instant = datetime_from_local(wall, tokyo)
```

ホスト環境のローカルゾーンは参照しません。夏時間移行によって該当時刻が存在しない
場合はnonexistent-timeエラー、二度存在する場合はambiguous-timeエラーにします。
v0.2は時刻を勝手に進めず、早い方・遅い方のどちらも自動選択しません。呼び出し側は
オフセット付き`datetime(...)`で意図する瞬間を明示できます。

表示ゾーンの変更は瞬間を変更しません。

```separan
in_tokyo = datetime_in_timezone(utc, tokyo)
```

## 現在時刻

現在時刻にはtimezone値が必須です。

```separan
tokyo = timezone("Asia/Tokyo")
now = datetime_now(tokyo)
```

引数なし`datetime_now()`や暗黙のシステムローカル時刻は存在しません。テストや
組み込み利用者は時計を注入できる必要があり、適合テストは実時間へ依存しません。

## duration文字列

`duration(string)`は、順序固定・重複不可の整数要素を使います。

```text
[-][<days>d][<hours>h][<minutes>m][<seconds>s][<milliseconds>ms]
```

少なくとも1要素が必要です。

```separan
duration("0s")
duration("250ms")
duration("1h30m")
duration("2d4h5m6s")
duration("-30m")
```

空白、小数、単位重複、単位順序違反、未対応単位はエラーです。したがって、
`1.5h`、`30m1h`、`1h20h`、`1 month`、`1mo`、`1y`は不正です。
各要素は通常の時計範囲を超えてもよく、`90m`は有効です。string変換時には
`1h30m`へ正規化します。
正規化後の合計は符号付き64bitミリ秒
（`-9223372036854775808`～`9223372036854775807`）へ収まる必要があります。

## 演算子

次の時間演算だけを定義します。

| 式 | 結果 |
|---|---|
| `datetime + duration` | `datetime` |
| `duration + datetime` | `datetime` |
| `datetime - duration` | `datetime` |
| `datetime - datetime` | `duration` |
| `duration + duration` | `duration` |
| `duration - duration` | `duration` |
| `duration * number` | `duration` |
| `number * duration` | `duration` |
| `duration / number` | `duration` |
| `duration / duration` | `number` |

`datetime + datetime`、`local_datetime`や`timezone`を含む算術、および表にない
組み合わせは型エラーです。経過時間を加算した結果は左辺datetimeの表示ゾーンを
維持します。IANAゾーンでは`24h`の加算は瞬間を正確に24時間進めるため、夏時間の
境界をまたぐと表示上の現地時刻が変化する場合があります。

durationの乗除算結果は正確な整数ミリ秒でなければなりません。ゼロ除算や精度を
失う結果を丸めず、エラーにします。

## 比較

- `datetime`の順序と等価性は表示フィールドではなく瞬間を比較。
- `local_datetime`は別の`local_datetime`と暦・時計フィールドを比較。
- `duration`は経過時間長を比較。
- `timezone`の等価性は正規化したゾーンIDを比較。
- 既存のnull比較規則を除き、異なる時間型同士の比較は型エラー。

## 明示的UNIX変換

UNIX時刻は交換形式であり、Separanの標準時間型ではありません。

```separan
seconds = unix_seconds_from_datetime(instant)
millis = unix_milliseconds_from_datetime(instant)

a = datetime_from_unix_seconds(seconds, tokyo)
b = datetime_from_unix_milliseconds(millis, tokyo)
```

関数名には必ず単位を含めます。`timestamp()`や`datetime_from_unix()`のような
単位が曖昧な形式は存在しません。ミリ秒は整数値number、秒は最大ミリ秒精度の
小数部分を持てます。

## 正規string変換

v0.2では明示的`string(value)`を拡張します。

- `datetime`はオフセットを必ず含む。IANAゾーンは専用アクセサーで取得し、曖昧な
  接尾辞にはしない。
- `local_datetime`はオフセットを含まない。
- `timezone`は正規化した識別子を使う。
- `duration`は符号と正規化済みの順序付き要素を使う。

正規化された文字列表現を再度パースすると、同じ型の等価な値を復元できなければ
なりません。
ロケール依存の人間向け表示は将来の別APIです。

## 最小イントロスペクション関数

```text
datetime_offset(value)        -> duration
datetime_timezone(value)      -> timezone
datetime_year(value)          -> number
datetime_month(value)         -> number
datetime_day(value)           -> number
datetime_hour(value)          -> number
datetime_minute(value)        -> number
datetime_second(value)        -> number
datetime_millisecond(value)   -> number
duration_milliseconds(value)  -> number
```

フィールド取得は明示的です。初期実装ではプロパティ構文を必要としません。

## 診断

時間サブシステムは次の診断概念を予約します。v0.2公開後は数値コードを安定させます。

| コード | 分類 |
|---|---|
| `E401` | 不正なdatetime文字列 |
| `E402` | timezoneの欠落または禁止された付与 |
| `E403` | 未知または不正なtimezone |
| `E404` | 不正なlocal datetime文字列 |
| `E405` | 曖昧なlocal datetime |
| `E406` | 存在しないlocal datetime |
| `E407` | 不正なduration文字列 |
| `E408` | 不正な時間演算 |
| `E409` | 時間精度の損失 |

すべての診断は、入力、受理可能な形式または演算の組み合わせ、修正方法を含めます。
DST診断にはlocal値とzoneを含め、オフセットを黙って選択してはいけません。

## 実装要件

- ASTは通常の呼び出し・演算子ノードを保持し、ランタイム値には将来のSemantic
  Tokensで使える個別の時間型タグを持たせる。
- リファレンス実装は標準時間ライブラリを利用できるが、ホスト言語のオブジェクトを
  Separan値として露出しない。
- datetimeの保存は表示timezoneから独立し、ミリ秒精度で決定的にする。
- timezoneデータベースのバージョンと更新方針を文書化する。
- オーバーフロー限界を明示し、ホスト言語例外ではなくSeparanエラーにする。
- 適合テストは固定tzdb fixtureでDSTのgapとoverlapを検証する。

## 将来へ送る概念

暦上の月・年には将来の`calendar_period`設計が必要です。ロケール表示、営業日、
タイマー、sleep、スケジューリング、失敗可能な`try_datetime` APIは、この初期時間
仕様の対象外です。
