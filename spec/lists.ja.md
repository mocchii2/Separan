# list — 非破壊操作

状態: **リファレンス実装へ実装済み。**

Separan v0.1の可変長コレクション型は`list`一つです。arrayとlistを分離しません。
インデックスは0始まりで、要素は一つの公開型に統一します。

```separan
numbers = [10, 20, 30]
names = ["alice", "bob", "carol"]
first_number = numbers[0]
```

`[1, "a", true]`は型エラーです。空listの要素型は未確定で、`list_append`などに
よって非空の値が代入された時点で確定します。

## 非破壊API

すべてのlist操作は入力listを変更せず、結果を返します。v0.1には破壊的list関数も
インデックス代入もありません。

| 関数 | 結果 |
|---|---|
| `list_append(items, value)` | 末尾へ`value`を加えた新しいlist |
| `list_remove(items, value)` | 最初に一致した値を除いた新しいlist |
| `length(items)` | 要素数。推奨する共通名 |
| `size(items)` | `length`のlist専用互換alias |
| `is_empty(items)` | listが空か |
| `first(items)` | 最初の要素 |
| `last(items)` | 最後の要素 |
| `contains(items, value)` | 一致する値が存在するか |
| `index_of(items, value)` | 最初に一致する0始まりindex。不在ならnull |
| `last_index_of(items, value)` | 最後に一致する0始まりindex。不在ならnull |
| `slice(items, start, end)` | 半開区間`[start, end)`の新しいlist |
| `reverse(items)` | 逆順の新しいlist |
| `sort(items)` | 昇順・安定sort済みの新しいlist |

`list_append`の新しい値は確定済み要素型と一致する必要があります。
`list_remove`は最初の一致だけを削除し、不在ならエラーにします。変更されていないlistを
黙って返しません。検索値は要素型と一致する必要がありますが、一般のnull比較規則に
従いnullの検索は許可します。

`first`と`last`は空listを拒否します。`index_of`と`last_index_of`では不在が通常の
検索結果なのでnullを返し、制御フロー上で明示できます。

```separan
index = index_of(items, target)
if index != null :target_found
print index
endif:target_found
```

sliceのindexは`0 <= start <= end <= length(items)`を満たす必要があります。負数、小数、
逆転、範囲外はエラーです。v0.1の`sort`は同型number listまたはstring listだけを
扱います。numberは数値順、stringはUnicodeコードポイント順で、安定sortです。

`contains`はbooleanの包含判定という意味が同一なためstringと共有します。どちらの
オペランドも暗黙変換しません。

## forとの連携

```separan
for item in items :each_item
print item
endfor:each_item
```

ループ変数は現在の関数またはglobal scopeに属します。反復は新しいscopeを作らず、
listも変更しません。

## 診断

| コード | 分類 |
|---|---|
| `E302` | `items[index]`の範囲外アクセス |
| `E602` | 空listアクセス |
| `E603` | 不正なlist範囲 |
| `E604` | list値が見つからない |

要素型違反は共通の`E201`を使います。破壊的API、メソッド呼び出し構文、固定長array型は
将来へ送ります。
