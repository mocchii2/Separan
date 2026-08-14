# 読みやすい数学機能 — v0.2.0-alpha.2

Separanの数学機能は、人間のコードレビューで意味が名前から分かることを優先します。
暗黙変換は行わず、結果はすべて`number`です。定義域外、非有限、複素数になる演算は
NaNやinfinityを黙って返さず`E308`になります。

## 命名と互換性

読みやすい長い名前を推奨表記とします。既存の`abs`、`min`、`max`、`sqrt`、`pow`、
`exp`、`log`、`log2`、`log10`はalpha期間中、予約済み互換aliasとして残します。

変換名は`source_to_target`を原則とします。例えば
`number_to_hexadecimal()`と`hexadecimal_to_number()`です。

## 数値リテラル

```separan
decimal = 1_000_000
fraction = 12_345.67_89
binary = 0b1111_0000
octal = 0o755
hexadecimal = 0xff_ff
```

prefixは大文字小文字を区別しません。区切りの`_`は、選択した基数で有効な数字と
数字の間にだけ置けます。負号はliteralの一部ではなく単項`-`演算子です。
指数表記は定義しません。

不正な数字、数字の欠落、先頭・末尾・連続する区切り、基数付き小数はLexerの
`E101`になります。

## 基本数値操作

| 関数 | 規則 |
|---|---|
| `absolute(value)` | 絶対値 |
| `minimum(values)` / `maximum(values)` | 空でない`list<number>`。複数のnumber引数も許可 |
| `round(value[, digits])` | 10進丸め。完全な中間値は0から遠い方。digitsは`-100..100`の整数値number |
| `truncate(value)` | 小数部を0方向へ切り捨て |
| `clamp(value, minimum, maximum)` | `minimum <= maximum`必須 |
| `sign(value)` | `-1`、`0`、`1` |

## 累乗・対数・角度

| 分類 | 関数 |
|---|---|
| 平方根・累乗 | `square_root`、`cube_root`、`power`、`hypotenuse` |
| 指数 | `exponential`、`exponential_base2` |
| 対数 | `natural_log`、`log_base2`、`log_base10`、`log_one_plus` |
| 三角関数 | `sin`、`cos`、`tan`、`arc_sin`、`arc_cos`、`arc_tan`、`arc_tan2` |
| 双曲線関数 | `sinh`、`cosh`、`tanh`、`arc_sinh`、`arc_cosh`、`arc_tanh` |
| 角度変換 | `to_radians`、`to_degrees` |

三角関数の入力と逆関数の結果はradianです。`arc_tan2(y, x)`は引数順も仕様として
固定します。

## 整数値操作と状態判定

`greatest_common_divisor(a, b)`、`least_common_multiple(a, b)`、
`factorial(value)`は数学的な整数値を要求し、`5.0`も許可します。
factorialはresource使用を制限するため`0..1000`です。

`is_finite`、`is_infinite`、`is_nan`、`is_close`、`is_integer_value`はnumberを要求し、
厳密なbooleanを返します。`is_close(a, b)`はrelative tolerance `1e-9`、
absolute tolerance `0.0`です。

## 統計

統計関数はすべて同型の`list<number>`を要求し、元listを変更しません。

| 関数 | 規則 |
|---|---|
| `median(values)` | 中央値。偶数個では中央2値の平均 |
| `variance(values)` | 母分散。分母は`n` |
| `sample_variance(values)` | 標本分散。分母は`n - 1`、2値以上 |
| `standard_deviation(values)` | 母標準偏差 |
| `sample_standard_deviation(values)` | 標本標準偏差、2値以上 |
| `percentile(values, percent)` | `percent`は`0..100`。順位`(n - 1) * percent / 100`で線形補間 |
| `moving_average(values, window)` | 連続区間の平均。`1 <= window <= length(values)` |

空または不足したcollectionは`E602`、不正なpercentile、window、精度、基数、factorial、
大小範囲は`E308`です。

## 進数変換

`number_to_binary`、`number_to_octal`、`number_to_hexadecimal`はprefixなしの小文字stringを
返します。逆変換は先頭の`-`と数字間の区切りを許可しますが、入力元の基数が関数名で
明示済みなので`0b`、`0o`、`0x`prefixは許可しません。

`number_to_base(value, base)`と`base_to_number(text, base)`は2～36進数に対応し、
出力は小文字`0-9a-z`、入力は大文字小文字を区別しません。数値引数は整数値必須で、
不正な文字列は`E304`です。

数学定数と`math.*`名前空間は、module／namespace方針が安定するまで保留します。
