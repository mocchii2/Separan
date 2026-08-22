# EMPTY、EMPTYS、VOID — v0.2段階仕様

Separanは、従来`null`が曖昧にしていた3つの状態を分離します。

- `EMPTY`: 型付きの単一value slotが現在値を持たない。
- `EMPTYS`: 型付きcontainerが構造を保ったまま有効値を持たない。
- `VOID`: 関数が値を生成せず終了した。

`EmptyValue`と`VoidResult`は異なるruntime表現です。関数末尾への到達と値なし`return`は
`VOID`を生成します。`VOID`は代入、表示、引数渡し、list格納、演算に利用できません。

EMPTYの判定には専用の状態構文だけを使います。

```separan
if value is EMPTY :value_missing
print "No value"
endif:value_missing

if value is not EMPTY :value_present
print value
endif:value_present
```

`is`は一般的な等値演算子ではありません。`value is 1`、`value is null`、状態判定と
比較の連鎖は構文errorです。通常値の一致判定には引き続き`==`と`!=`を使います。

型付き変数はEMPTY状態で開始でき、後から宣言型の値だけを受け取れます。既存の可変
bindingへEMPTYを代入すると、型を残して値だけを消します。型なしの初回代入では
EMPTYから型を推論できず、constをEMPTYにすることもできません。

```separan
number age = EMPTY
age = 30
age = EMPTY
age = 31       # 有効。ageはnumberのまま
```

型付き引数と型付きobject fieldにも同じ規則を適用します。`is EMPTY`による状態取得と
`type_of()`による保持型取得は有効です。値を再設定する前の表示、演算、index、条件、
実値を要求するAPI利用は`E131`になります。

listの各slotは、listの同型element規則を保ったまま個別にEMPTYへできます。index代入は
0始まりで明示します。

```separan
list<number> values = [10, 20, 30]
values[1] = EMPTY
values[1] = 25
```

型付きlist literalにはEMPTYを含められます。推論型listではelement型を決定するため
1個以上の実値が必要です。このため`[1, EMPTY]`は`list<number>`ですが、型なしの
`[EMPTY, EMPTY]`は`E134`です。

EMPTYSはcontainer構造を保ったまま有効値をすべて消します。listではslot数を維持して
各slotを型付きEMPTYへ変え、objectではfield、field型、nested container形状を維持します。

```separan
values = EMPTYS

if values is EMPTYS :no_values
print length(values)
endif:no_values
```

空list／object、および全slot／fieldがEMPTYのcontainerは`is EMPTYS`を満たします。
`list<number> values = EMPTYS`は空の型付きlistを初期化します。objectには保持対象fieldが
ないためEMPTYSで初期化できず、scalarや個別list slotにもEMPTYSを代入できません。

残る移行は、JSON null変換、標準API移行、最後にsource-level `null`削除の順で進めます。
