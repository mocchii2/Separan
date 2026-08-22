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

残る移行は、型付きEMPTY格納、object field、list要素とEMPTYS、JSON null変換、
標準API移行、最後にsource-level `null`削除の順で進めます。

