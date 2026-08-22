# list shape操作 — v0.2 preview

状態: **リファレンス実装へ実装済み。**

Separanはlistの値とslot shapeを別の概念として扱います。

- `value = EMPTY`は1値だけを消し、slotとelement型を維持します。
- `container = EMPTYS`は全有効値を消し、nested slot数、jagged shape、型を維持します。
- `list_insert`はtyped `EMPTY`で初期化したslotを追加します。
- 3引数の`list_remove`はslotを削除します。

```separan
list<number> values = [10, 20, 30]
values[1] = EMPTY                 # [10, EMPTY, 30]、長さ3
values = EMPTYS                   # [EMPTY, EMPTY, EMPTY]、長さ3
list_remove(values, front, 3)     # []、長さ0
```

element型を明示すれば、全slotがEMPTYのshapeも宣言できます。

```separan
list<number> values = [EMPTY, EMPTY, EMPTY]
values[0] = 100
values[2] = 300
```

`values = [EMPTY, EMPTY, EMPTY]`では保持するelement型を推論できないためerrorです。

## 位置selector

shape APIの位置には`front`、0始まりの非負整数、`back`を使います。`front`と`back`は
通常値ではなく文脈限定selectorなので、`x = front`は`E136`です。insertの`back`は
`length(values)`、removeの`back`は末尾から`count` slotを意味します。`count`は正の整数
だけを許可し、変更前に全rangeを検証します。

## 1次元操作

```separan
list_insert(values, position, count) -> VOID
list_remove(values, position, count) -> VOID
```

対象は直接の可変list bindingまたはindexed rowでなければなりません。`const`、一時式、
戻り値の代入には使えません。

```separan
list<number> values = [10, 20, 30]
list_insert(values, 1, 2)         # [10, EMPTY, EMPTY, 20, 30]
list_remove(values, back, 2)      # [10, EMPTY, EMPTY]
```

既存の2引数`list_remove(values, value) -> list`は非破壊の互換APIとして維持します。
3引数なら副作用を持つshape操作として一意に解釈します。

## nested／jagged list

nested型宣言は再帰的で、rowの長さを揃える必要はありません。

```separan
list<list<number>> values = [[1, 2], [3, 4, 5], [6]]
values[1][1] = EMPTY
values[1] = EMPTYS
values = EMPTYS
```

最後の`EMPTYS`後も3 rowと長さ2、3、1を維持します。outer listへのshape操作はrowを
増減し、`values[row]`への操作はそのrowだけを変更します。outerへ追加したslotは
`EMPTY<list<number>>`であり、内側shapeを推測しません。

## 方向付き削除

```separan
list_remove_horizontal(values, row, column, count) -> VOID
list_remove_vertical(values, row, column, count) -> VOID
```

horizontal removeは一つのrowからslotを削除して後続値を左へ詰めます。1次元removeを
rowへ直接適用する操作と同じ効果ですが、方向を明示します。

vertical removeは`row`以降の一つのcolumnだけを上へshiftし、空いた下端cellをtyped
`EMPTY`で埋めます。outer／inner slot数は維持され、row削除ではありません。jagged listでは
影響する全rowに対象columnが必要です。操作全体を先に検証するため、shape error後に
部分変更が残ることはありません。

vertical insertはjagged listの拡張規則が確定するまで保留します。矩形を推測してpadding
することはありません。

## 診断

| code | 意味 |
|---|---|
| `E134` | 追加EMPTY slotのelement型が未確定 |
| `E136` | `front`／`back`を位置文脈外で使用 |
| `E211` | `const` bindingの変更 |
| `E603` | position、count、row、column、rangeが不正 |
| `E605` | 直接の可変listでない、またはjagged検証失敗 |

