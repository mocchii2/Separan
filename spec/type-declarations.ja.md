# 明示的型宣言 — v0.2設計

Separanは通常、最初の代入から変数の固定型を推論します。明示的型宣言は、その固定型を
ソースへ記述し、初期値を即座に検査します。

```separan
number count = 0
string name = "Separan"
boolean enabled = true
list<number> values = []
const string version = "0.2"
```

すべての宣言で`= value`が必須です。`string name`のような裸の宣言は禁止します。
意図的な未設定と初期値の書き忘れを区別できないためです。意図的に初期値を
持たせない場合は`string name = EMPTY`と記述します。

初期値は宣言型と完全に一致しなければならず、暗黙変換は行いません。型付きlistは
空listで初期化する場合も要素型が必須で、その後の代入でも要素型を維持します。

```separan
list<number> values = []
values = [1, 2]       # 有効
values = ["one"]      # E201
```

明示的型宣言は新しいbindingを作ります。同じscopeで同じ名前を再宣言するとerrorです。
通常の再代入は、宣言済み固定型の範囲内で値を更新します。
`const type name = value`は型付き定数を作ります。

関数引数の型注釈では、読み手が引数名を先に認識できるよう名前を先に書きます。

```separan
function:show_age(age: number, labels: list<string>)
...
end_function:show_age
```

型付き引数は`EMPTY`を直接受け取れます。型なし引数が受け取れるのは、呼び出し元の
bindingから型を保持しているEMPTYだけです。生のEMPTYから引数型を推論しません。

object blockのfieldも変数と同じ宣言形式です。

```separan
object:user
string name = EMPTY
number age = 30
end_object:user
```
