# module・data・I/O・error — v0.2設計

状態: **一部プレビュー実装済み。** label付きobject/list、member access、非破壊object
API、namespace付きimport、`try/catch/finally/throw`、標準stream、高level file I/O、
JSON、root／environment allowlist capabilityを利用できます。

相互依存する機能を次の順番で実装します。先頭2段とerror処理はpreview済みです。

```text
object／block list値 → namespace付きimport → I/OとJSON → label付きerror処理
```

構造化された値モデルとcatch可能なerrorモデルがない状態で、file／JSON失敗だけを
場当たり的に公開しません。

capability型HTTPはnamed argument、object、label付きcatch可能errorの後に実装します。
個別の[HTTP設計](http.ja.md)を参照してください。

外部processも同じhost capability modelに従い、個別の
[process実行設計](process-execution.ja.md)で定義します。

## const

constは実装済みです。

```separan
const pi = 3.14159
const app_name = "Separan"
```

`const`なしの名前は可変です。constは自身のscope内で再代入できません。同じscopeの
mutable／const名重複はエラーです。globalとfunction localは別scopeなので、local
bindingはglobal constを変更せずshadowできます。`const`は浅い不変性です。将来
object／list値を持てるようになった際、binding先は変更できませんが、値そのものの
不変性は別途仕様化します。

## label付きdata block

Separan sourceにはJSONの`{}`／`[]`記法を導入しません。人が書く構造化dataは、
他の構造と同じく名前付きblockで表現します。

```separan
object:user
name = "Alice"
age = 30
active = true

object:address
city = "Tokyo"
zip = "100-0001"
end_object:address
end_object:user

list:users
"Alice"
"Bob"
"Carol"
end_list:users
```

top-levelまたはfunction bodyの`object:user`は`user` bindingを作ります。object内の
`object:address`／`list:roles`は同名fieldへ値を設定します。開始名と終了labelは完全一致
しなければなりません。indentationは引き続き装飾です。

初期規則:

- object field名はidentifierで、同じobject内で一意。field値は異型でよい。
- block listは既存listと同じく同型・0始まり。空listは最初の追加時に型が決まる。
- object／listの構築完了前に自身を参照できない。
- `user.name`は存在するidentifier fieldへのaccess。欠落fieldはnullではなくerror。
- JSON由来の任意string keyには`object_get(value, key)`、`object_has`を使う。これにより
  `x-api-key`のようなidentifierでないkeyも失わない。
- 更新APIは非破壊とし、source blockの重複fieldを黙って上書きしない。
- `{}`は将来もcontrol block／data literalのどちらにも使わない。`[]`式list literalを
  廃止するかは互換性判断を伴うため別途決定するが、block listを標準の複数行記法とする。

これはJSON構文の別名ではありません。Separan object/listはlanguage valueであり、
JSONは明示的な境界変換だけに使います。

## namespace付きimport

初期module構文は一つに限定します。

```separan
import "utils/math.sep" as math
result = math.add(10, 20)
```

- `as alias`必須。修飾なしimportは禁止。
- importはtop-levelだけで、実行可能なtop-level文より前。
- pathはUTF-8 stringで、import元fileからの相対解決。
- `.sep`拡張子必須。
- 初期実装では絶対pathと`..` traversalを拒否。
- moduleはtop-level functionとconstを公開。mutable globalは初期実装ではprivate。
- import bindingはnamespace経由。caller scopeへの名前copyは延期。
- canonical pathでcacheし、moduleの実行は最大1回。

循環importは完全なcanonical chainを表示するエラーです。

```text
SEPARAN E701: Circular import

a.sep
→ b.sep
→ a.sep
```

埋め込みAPIとCLIは明示的project rootを受け取れる必要があります。任意の作業directory
やenvironment pathを検索しません。

## 標準入出力

```separan
name = input("Name: ")
print name
print_error "Invalid value"
```

`input(prompt)`は改行なしで標準出力へpromptを書き、行末を除いた1行を返します。
EOFは空stringではなく`io_error`です。`print_error`は`print`と並ぶstatementで、
標準errorへ改行付きで出力します。決定的テストのためstreamは注入可能にします。

## 高level file I/O

初期APIはhandleを公開しません。

```separan
text = read_text("config.txt")
write_text("output.txt", text)
append_text("log.txt", "hello\n")

data = read_bytes("image.bin")
write_bytes("copy.bin", data)
```

- textはUTF-8。不正UTF-8は具体的な`io_error`。
- text書き込みはBOMなしUTF-8。
- pathはhostが渡す明示的capability rootから解決。
- absolute pathとroot外へのescapeを禁止。
- `write_text`／`write_bytes`はplatformで可能ならtemporary file経由の置換とし、
  partial writeを成功扱いしない。
- string／bytesの暗黙変換は行わない。
- 低level file handleは延期。

埋め込みhostはfile I/Oを完全に無効化できます。権限なしはfile不在ではなく個別の
`permission_error`です。

## JSON

JSONはobject／list実装後に導入します。API名は変換であることが明確な
`json_decode`／`json_encode`に固定します。

```separan
data = json_decode(text)
text = json_encode(data)
```

- JSON object → `object`
- JSON array → 同型`list`。異型arrayは初期実装では拒否。
- JSON number → `number`
- JSON string、boolean、nullは直接対応。
- object key重複は`parse_error`。
- 非有限numberを拒否。
- `json_encode`は決定的。object keyをUnicodeコードポイント順に出力し、不要空白なし。
- 初期の非破壊APIでは循環値は作れない。

Separanのlist型を弱めず、正当でも異型なJSON arrayを意図的に拒否する初期subsetです。
decodeしたJSONを再度source codeとして出力する機能は標準JSON APIに含めません。
**JSONは通信formatとして使うが、人間向けSeparan sourceには書かせません。**

## label付きerror処理

```separan
try :load_config
text = read_text("app.json")
data = json_decode(text)

catch io_error :load_config
print_error "Could not read app.json"

catch parse_error :load_config
print_error "Invalid JSON"

finally:load_config
print "done"
endtry:load_config
```

規則:

- 全`catch`、`finally`、`endtry`のlabelは開始`try`と一致。
- 0個以上のcatchの後に最大1個のfinally。
- `catch any`は最後。
- catch type重複はエラー。
- tryへ入った後は、returnや新しいerrorを含めfinallyが必ず実行。
- finallyがthrowしたら新errorをactiveにし、元errorを関連診断として保持。
- matching catchまでerrorを伝播し、nullやdefault値へ黙って変換しない。

初期catch category階層:

```text
runtime_error
├─ type_error
├─ value_error
├─ index_error
├─ io_error
├─ parse_error
├─ import_error
├─ regex_error
├─ glob_error
├─ argument_error
└─ permission_error
```

`catch runtime_error`は列挙したruntime categoryをすべて捕捉します。`catch any`は将来の
user-defined categoryも捕捉します。parser／compile-time診断はprogramからcatch
できません。

組み込みerror categoryは明示的constructorを使います。

```separan
throw value_error("invalid age")
```

`throw`はerror値を要求するstatementです。stringを直接throwすることは禁止します。
custom errorは空のlabel付きtop-level宣言です。

```separan
error:payment_error
end_error:payment_error

throw payment_error("card declined")
```

名前は`_error`で終わり、組み込みcategory・function・別errorと衝突できません。custom
errorは自身のcategory、`runtime_error`、`any`でcatchできます。fieldや継承指定は将来です。

## 計画診断範囲

| 範囲 | 領域 |
|---|---|
| `E701`～`E709` | import／module |
| `E720`～`E729` | I/O／capability |
| `E740`～`E749` | JSON |
| `E760`～`E769` | try/catch/finally／throw |

個別codeは実装前に確定し、関連preview公開後は安定させます。
