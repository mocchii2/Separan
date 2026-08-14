# Separan言語仕様 — v0.2.0-alpha.1

この文書は現在の言語仕様の簡潔な規範文書です。実行可能な適合条件は
`tests/`のテストとして管理します。

## 中心規則

空白はブロック構造を決定しません。ブロックは種類とラベルで識別します。
終了側の種類とラベルは、最後に開かれたブロックと一致する必要があります。

```separan
if condition :label
...
endif:label
```

同じ規則を`while`/`endwhile`、`for`/`endfor`、および
`function:name`/`end_function:name`へ適用します。同時に開いている構造識別子は
同じ名前空間に属し、一意でなければなりません。閉じたラベルは再利用できます。

## v0.2 alphaの規則

- ソースはUTF-8の`.sep`ファイル。
- 1行1文。セミコロンは使用しない。
- 識別子は`[A-Za-z_][A-Za-z0-9_]*`。明示的なblock label、複数行comment label、function tagには
  NFC正規化済みUnicode identifierも使用できる。どちらも大文字小文字を区別し、絵文字、
  空白、句読点、非正規化labelは使用できない。
- 型は`number`、`string`、`boolean`、`list`、`null`。
- 変数は最初の代入で推論した型を維持する。
- 関数引数は、その関数への最初の呼び出しで型を固定する。
- リスト要素は同一型。インデックスは0始まりの非負整数。
- 条件はboolean必須。truthy/falsy変換は行わない。
- 文字列、数値、boolean間の暗黙変換は禁止する。
- 比較演算子の連鎖は禁止し、`&&`で明示する。
- `main()`は自動実行し、引数を持てない。
- `main`がなければトップレベルの代入と`print`を順に実行する。
- `const name = value`は現在のscopeに再代入不能bindingを作る。

## 演算子

演算子は暗黙変換を行いません。優先順位は低い順に`??`、`||`、`&&`、等値比較、
大小・包含比較、`+ -`、`* / // %`、単項`! not -`、`**`です。`**`は右結合。
`??`も右結合で、左辺がnullの場合だけ右辺を評価します。

| 演算子 | 規則 |
|---|---|
| `+ - * / %` | number演算。`+`は同型string、bytes、同型listの連結にも使う |
| `//` | 整数専用floor除算。負の結果は負の無限大方向へ丸める |
| `**` | 実数かつ有限結果の累乗 |
| `== != < <= > >=` | 変換なしの厳密比較。比較連鎖は禁止 |
| `&& || ! not` | boolean専用。`&&`と`||`は短絡評価 |
| `??` | null専用fallback。false、0、空値はそのまま保持 |
| `in`、`not in` | string、list、object field名、bytesの厳密な包含判定 |

複合代入は`+=`、`-=`、`*=`、`/=`、`//=`、`%=`、`**=`を提供します。対応する演算後に
代入するのと同じなので、constは変更できずbindingの固定型規則も維持します。`??=`はnull型bindingを
別型へ変える抜け道になるため提供しません。`++`と`--`も定義しません。

string包含は両方string、list検索値は同型element、objectはstring field名を要求します。
bytesはbytes部分列または0..255の整数byteを検索できます。不在はfalseですが、検索型不一致を
黙ってfalseにはせずtype errorとします。

## 組み込み関数

組み込み関数名は予約され、ソースプログラムから再定義できません。

| 関数 | 受け付ける値 | 結果 |
|---|---|---|
| `length(value)` | string、list、bytes | Unicodeコードポイント数、要素数、バイト数 |
| `is_empty(value)` | string、list、bytes | 長さが0か |
| `len(value)` | string、list、bytes | `length`の互換alias |
| `type(value)` | 任意の値 | ユーザー向け型名のstring |
| `type_of(value)` | 任意の値 | ユーザー向け型名の読みやすいalias |
| `is_null(value)` | 任意の値 | nullとの完全一致判定 |
| `is_number/string/boolean/list/object(value)` | 任意の値 | 公開型との完全一致判定 |
| `is_bytes/datetime/duration/secret(value)` | 任意の値 | 公開型との完全一致判定 |
| `abs(value)` | number | 数値の絶対値 |
| `ceil(value)`／`floor(value)` | number | 整数値の天井／床。公開型はnumber |
| `round(value)` | number | 近い整数値。完全な中間値は0から遠い方へ丸める |
| `min(values...)`／`max(values...)` | 1個以上のnumber | 最小値／最大値 |
| `sqrt(value)` | 非負number | 有限の平方根 |
| `sin(value)`／`cos(value)`／`tan(value)` | ラジアンのnumber | 有限の三角関数結果 |
| `log(value)` | 正のnumber | 自然対数 |
| `log10(value)`／`log2(value)` | 正のnumber | 底10／底2の対数 |
| `exp(value)` | number | 有限の`e`のべき乗 |
| `pow(base, exponent)` | number | 有限の実数べき乗 |
| `range(stop)` | 整数値number | 0から`stop`未満までのlist |
| `range(start, stop)` | 整数値number | `start`から`stop`未満までのlist |
| `range(start, stop, step)` | 整数値number、stepは0以外 | step間隔のnumber list |
| `number(value)` | numberまたは厳密な10進string | number |
| `string(value)` | number、string、boolean、null | 正規化したstring表現 |
| `boolean(value)` | booleanまたは完全一致する`"true"`／`"false"` | boolean |

`range`は`step`の方向に進み、`stop`へ到達できない方向なら空listを返します。
整数と浮動小数点はユーザーからは同じnumber型ですが、`range`は浮動小数点と
booleanを拒否します。

変換は明示的かつ厳密です。`number`が受け付ける10進文字列は
`-?[0-9]+(?:\.[0-9]+)?`に一致するものだけで、前後空白、先頭の`+`、指数表記は
拒否します。`boolean`はtruthy/falsy変換を行いません。数値、null、list、および
小文字の`"true"`と`"false"`以外の文字列はエラーです。`string`はv0.1ではlistを
シリアライズしません。文字列内容の変換失敗は`E304`になります。

将来の失敗可能な変換は、デフォルト値で失敗を隠す形式より、
`try_number(value) -> number | null`のように制御フロー上へ失敗を明示する形式を
優先します。

### 文字列関数

位置と長さはすべてUnicodeコードポイント単位です。文字列以外の引数を暗黙変換
する関数はありません。

| 関数 | 結果 |
|---|---|
| `trim(value)` | 両端のUnicode空白を除去 |
| `upper(value)` | Unicode大文字変換 |
| `lower(value)` | Unicode小文字変換 |
| `contains(value, search)` | `search`を含むか |
| `starts_with(value, prefix)` | `prefix`で始まるか |
| `ends_with(value, suffix)` | `suffix`で終わるか |
| `split(value, delimiter)` | 空でない区切り文字で分割した同一string型list |
| `join(values, separator)` | stringだけを含むlistの結合 |
| `replace(value, search, replacement)` | 空でない`search`をすべて置換 |
| `substring(value, start)` | `start`から末尾まで |
| `substring(value, start, end)` | 半開区間`[start, end)`の文字列 |
| `reverse(value)` | Unicodeコードポイント単位の逆順。listにも共通 |
| `char_at(value, index)` | 有効な0始まりindexの1コードポイントstring |
| `find_all(value, search)` | 非重複literal一致のindex list。不在なら空list |
| `index_of(value, search)` | 最初のコードポイントindex。不在ならnull |
| `last_index_of(value, search)` | 最後のコードポイントindex。不在ならnull |
| `repeat(value, count)` | 非負整数回繰り返したstring |
| `pad_left(value, length[, fill])` | 最低target長まで左padding |
| `pad_right(value, length[, fill])` | 最低target長まで右padding |

substringのインデックスは`0 <= start <= end <= len(value)`を満たす必要があります。
負数、小数、逆転、範囲外はエラーです。空の区切り文字と空の置換検索文字列は
`E305`、不正なsubstring範囲は`E306`になります。

string検索位置はUnicodeコードポイント単位です。単一検索の不在時は`-1`ではなくnull、
`find_all`は空listを返します。空の検索文字列は`E305`で拒否します。paddingのfillは1コードポイントで、省略時は
半角空白です。repeatとpaddingの結果は1,048,576コードポイント以下に制限し、
無制限にメモリを確保せず`E607`を返します。

## コメント、Function Tag、文字列literal

`#`は行頭またはコードの後ろから行末までのコメントです。string内部の`#`は文字として
残ります。複数行コメントは一致する`##label`で囲み、labelなしの`##`／`##`も利用できます。
ネストは禁止です。`################################`のような装飾行は通常の1行コメントです。

`:`はStructural Identity専用です。Function先頭のmetadata領域に置く`@tag`は、実行結果を
変えずにSemantic IdentityをASTへ保持します。tagはNFC正規化済みUnicode identifierを許可し、
重複、Function外、最初の実行文より後への配置を拒否します。詳細は
[記号・Function Tag・文字列](symbols-tags.ja.md)を参照してください。

通常stringは`\\`、`\"`、`\n`、`\r`、`\t`、`\0`、`\uXXXX`、`\UXXXXXXXX`を
解釈します。未知、不完全、surrogate、範囲外のescapeはerrorです。`r"..."`はbackslashを
解釈しないRaw Stringです。

## 診断

診断には安定したコード、分類、ファイル、行、Unicodeコードポイント単位の列、
ソース行、ポインター、説明、可能な場合は期待値と実際値、関連する開始ブロックを
含めます。単なる`SyntaxError`だけの表示は仕様を満たしません。

LSPとAI編集範囲の強制は安定言語意味論の範囲外です。
[VS Code／LSP仕様](vscode-extension.ja.md)にeditor previewの実装状況と安全境界を記録します。
objectを含む以下の拡張仕様は実験実装済みですが、安定仕様ではありません。

## 実験実装済みの拡張仕様

- [時間型](temporal-types.ja.md): `datetime`、`local_datetime`、`timezone`、
  `duration`を分離して実装しています。安定版まではAPIが変更される可能性があります。
- [乱数](randomness.ja.md): 再現可能なPCG32とOS由来のセキュア乱数を分離し、
  不変の`bytes`型とともに実装しています。
- [list](lists.ja.md): 同型・0始まり・非破壊操作中心のlistを実装しています。
- [bytes](bytes.ja.md): stringと分離した不変binary値と明示的text／hex／Base64変換を実装しています。
- [認証とsecret](authentication.ja.md): 自動redactされるsecretと用途固定のHTTP、HMAC、JWT、OAuth、password APIを実装しています。
- [Cookie](cookies.ja.md): 単発Cookieとredactされるstateful Cookie Jarを実装しています。
- [module・data・I/O・error](modules-data-errors.ja.md): label付きobject／list、import、capability型I/O、
  JSON、const、label付きerror処理を実装しています。
- [HTTP client](http.ja.md): text中心取得、詳細response、正直なprofile、network
  capabilityを実装しています。browser automationとの境界も仕様として固定しています。
- [外部process実行](process-execution.ja.md): argv直接実行、checked実行、明示的shell
  risk、出力上限、host capabilityを実装しています。
- [regex・glob・environment・command line](system-utilities.ja.md): 検索不在、決定的な
  file探索、process内だけの環境変更、script名を分離した引数APIを実装しています。
- [構造AI workflow](structural-ai.ja.md): Parser連動block identity、AST-aware diff、
  structural／semantic tag scope検証、JSON review metadata、CI向けexit codeを実装しています。
- [Browser automation境界](browser-automation.ja.md): HTTP clientがbrowserを装わない、
  本物のengine用独立adapter契約を実装しています。
- [Structure Explorer](structure-explorer.ja.md): 人間向けblock階層、直接の
  reads／writes／calls、移動、Git構造状態を実装しています。
