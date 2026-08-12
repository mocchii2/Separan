# regex・glob・environment・command line — v0.2設計

状態: **実験的プレビュー実装あり。APIはv0.2まで変更される可能性があります。**

現在は全関数、名前付き引数、決定的glob、process内environment、command line snapshotを
利用できます。matchは`m.text`、`m.start`、`m.end`、`m.group(index)`を提供します。
互換用の`regex_text`／`regex_start`／`regex_end`／`regex_group`も利用できます。
regex engineの厳密なwork limitは、
正式v0.2化までの残作業です。

共通原則は次のとおりです。

> 検索対象が存在しないことが正常なら`null`または空listを返す。pattern、option、
> capabilityなど要求自体が不正な場合だけerrorにする。

## regex

```separan
ok = regex_match("^[0-9]+$", "12345")
found = regex_search("error", log, ignore_case = true)
match = regex_find("([0-9]+)-([A-Z]+)", text)
matches = regex_find_all("[A-Z]+", text)
text = regex_replace("[0-9]+", "***", source)
parts = regex_split("[,;]", source)
```

| API | 結果 |
|---|---|
| `regex_match(pattern, value[, options])` | string全体が一致したかをbooleanで返す |
| `regex_search(pattern, value[, options])` | 部分一致が存在するかをbooleanで返す |
| `regex_find(pattern, value[, options])` | 最初の`regex_match_result`またはnull |
| `regex_find_all(pattern, value[, options])` | 重ならないmatch resultのlist |
| `regex_replace(pattern, replacement, value[, options])` | 全一致箇所を置換したstring |
| `regex_split(pattern, value[, options])` | 区切ったstringのlist |

`regex_match_result`は不変の固定shape値で、`text`、`start`、`end`と
`group(index)`を持ちます。index 0は一致全体、存在するが不参加のgroupはnull、範囲外の
group番号はerrorです。位置はUnicodeコードポイント単位です。

初期flagはnamed argumentの`ignore_case`、`multiline`、`dot_all`だけです。flag文字列や
暗黙のlocale依存modeは導入しません。置換内の`$0`は全体、`$1`以降はcapture、`$$`は
literal `$`です。存在しないcapture参照はerrorです。

patternはUnicode対応のSeparan regex subsetとしてversion管理し、host言語固有の拡張を
そのまま公開しません。lookbehind、backreference、再帰patternは初期subset外です。
不正patternはfalseやnullではなく`regex_error`です。実装は入力長、pattern長、実行量に
上限を持ち、過大な処理も`regex_error`にして停止できなければなりません。

## file glob

```separan
files = glob("logs/*.log")
sources = glob("src/**/*.sep")
```

- 戻り値はproject rootからの相対pathを`/`区切りに正規化した`list<string>`。
- `**`だけがdirectory境界を越える再帰指定。別の`recursive` optionは設けない。
- 一致0件は空list。
- 結果はUnicodeコードポイント順で必ずsortし、filesystem列挙順を公開しない。
- `glob`はfileとdirectoryの両方を返す。`glob_files`／`glob_dirs`は必要性確認後に追加。
- dotfile／dot directoryはpattern segmentが`.`で始まる場合だけ一致。
- absolute path、`..`、project root外へのsymlink escapeを拒否。
- file read capabilityとは別の`path_discovery` capabilityをhostから要求する。

不正patternや権限不足は空listで隠さず、それぞれ`glob_error`／`permission_error`です。

## environment variable

```separan
path = env_get("PATH")
mode = env_get("APP_MODE", default = "production")

if env_exists("DEBUG") :debug_defined
print "debug"
endif:debug_defined

env_set("MODE", "test")
env_remove("MODE")
```

- `env_get`の不在結果はnull。defaultが明示された場合だけそのstringを返す。
- 名前と値はstringのみ。null、number、booleanへの暗黙変換は行わない。
- `env_set`／`env_remove`は現在のSeparan process環境と、その後起動する子processだけに
  影響する。OS全体、親process、永続user設定は変更しない。
- hostはread可能名とwrite可能名を別々にallowlistできる。
- capability外の名前は「不在」ではなく`permission_error`。
- platformの大小文字規則を隠さない。Windowsではcase-insensitive、POSIXでは
  case-sensitiveとして、同一process内で一貫させる。
- `env_all()`は秘密情報を一括露出するため初期標準APIに含めない。

## command line

```separan
args = command_args()
script = script_path()
verbose = arg_exists("-v", "--verbose")
source = arg_value("--source")
count = number(arg_value("--count", default = "1"))
```

- `command_args()`はscript名を含まない新しい`list<string>`を返す。
- `script_path()`はhostが解決したcanonical script pathを返す。stdin／埋め込み実行では
  nullを返す。
- `arg_exists(names...)`は、`--`より前に完全一致するoptionがあればtrue。
- `arg_value(name[, default])`は`--name value`と`--name=value`を認識する。
- option不在はnull、default指定時はdefault。optionがあるのに値がない場合は
  `argument_error`でありnullではない。
- 同じvalue optionが複数回あれば、黙って最後を選ばず`argument_error`。
- `--`以降はすべてposition引数で、option helperの検索対象外。
- 値は常にstring。型変換は`number()`、`boolean()`などで明示する。

完全なCLI schema blockは将来機能です。初期版はprocess起動時にhostから注入した引数の
snapshotだけを読み、programから書き換えません。

## 診断範囲

| 範囲 | 領域 |
|---|---|
| `E830`～`E839` | regex |
| `E840`～`E849` | glob／path discovery |
| `E850`～`E859` | environment |
| `E860`～`E869` | command line argument |
