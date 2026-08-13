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
| `sort_descending(items)` | 降順・安定sort済みの新しいlist |
| `sort_ignore_case(items)` | Unicode case foldを使う文字列の昇順sort |
| `sort_ignore_case_descending(items)` | 大文字小文字を無視する降順sort |
| `sort_natural(items)` | ASCII数字列を数値として比較する自然順sort |
| `sort_natural_descending(items)` | 自然順sortの降順版 |
| `sort_natural_ignore_case(items)` | 大文字小文字を無視する自然順sort |
| `sort_natural_ignore_case_descending(items)` | 大文字小文字を無視する自然順sortの降順版 |
| `sort_by(items, field)` | object listを指定fieldでsort |
| `sort_by_descending(items, field)` | object field指定sortの降順版 |
| `map(items, function)` | 全要素へ関数を適用。同型result list必須 |
| `filter(items, predicate)` | predicateがboolean trueの要素だけを残す |
| `reduce(items, function, initial)` | 必須の型固定初期値を使う左fold |
| `flatten(items)` | nested listをちょうど1階層だけ解除 |
| `sum(items)` | number listの合計。空listは0 |
| `average(items)` | 非空number listの算術平均 |
| `count(items, value)` | 完全一致する要素数 |

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
逆転、範囲外はエラーです。

## sort規則

すべてのsortは安定・決定的・非破壊です。通常の昇順／降順sortは、同型の`number`、
`string`、`datetime`、`local_datetime`、`duration` listを扱います。文字列の通常順は
Unicodeコードポイント順、大文字小文字無視版はUnicode case foldを使います。自然順版は
string専用で、ASCII数字列を数値として比較するため、`file2`は`file10`より前になります。
同じkeyの要素は入力順を維持します。

`sort_by`と`sort_by_descending`はobject listと空でないfield名を要求します。全objectが
fieldを持ち、field値が同一の比較可能型でなければなりません。fieldの欠落、型混在、boolean、
null、list、bytes、secretなど比較不能なkeyはエラーです。代替keyを推測したり、欠落値を
黙って末尾へ送ったりしません。

## 高階操作と集約

ユーザー関数名または組み込み関数名を値として渡すと、公開型`function`として`map`、
`filter`、`reduce`で利用できます。`map`はcallback結果の型混在を拒否します。`filter`は
実際のbooleanを要求し、truthy/falsy変換を行いません。`reduce`は`initial`を必須とし、
空listではそのまま返し、各accumulator結果は初期公開型を維持する必要があります。

`flatten`は1階層だけ解除し、結果の同型性を検証します。`sum([])`は`0`、未定義な
`average([])`は`E602`です。`count`の検索値は確定済み要素型と一致する必要があります。
`zip`はtuple型導入まで保留し、selectorを取る`*_by`はこれらの小さい操作の合成で表します。

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
