# 記号・Function Tag・文字列

状態: **preview実装済み**。

Separanでは記号の役割を分離します。

```text
#comment       人間向け説明
##label ...    複数行説明
:label         Structural Identity
@tag           Semantic Identity
```

## コメント

string外の`#`から行末までをコメントとします。行頭、コードの後ろ、装飾用の連続`#`を
同じ規則で扱います。

複数行コメントはNFC正規化済みlabelが一致する形式、またはlabelなし形式です。

```separan
##temporary
この範囲は無視される
##temporary

##
この範囲も無視される
##
```

ネストは禁止です。open中に異なるdelimiterが現れると`E104`、EOFへ達すると`E106`です。
旧`:`／`::label`コメントはbreaking syntaxとして廃止しました。

## Function Tag

tagは実行結果を変えないAST metadataです。

```separan
function:notify
@notification
@aws
@通知
send_message()
end_function:notify
```

Function宣言後、最初の実行文より前のmetadata領域だけに配置できます。tag行の周囲には
空行を置けます。名前は空白を含まないNFC正規化済みidentifierで、大文字小文字を区別します。
重複は`E218`、Function外は`E216`、実行文より後は`E217`です。

同じtagを持つFunction集合をSemantic Scopeとします。`separan-structure`はこの集合を
検索し、変更が集合内だけか検証できます。初期queryは曖昧な推測をせず、単一tagの完全一致です。

## Structural Completion

`:end`はeditor補完triggerであり、言語構文ではありません。補完は未close blockを内側から
順にopening line付きで表示し、`:end`全体を選択したcloserへ置換します。sourceに残した場合、
Parserは`E122`と有効なcloser一覧を返します。

## 文字列escape

通常stringは`\\`、`\"`、`\n`、`\r`、`\t`、`\0`、`\uXXXX`、
`\UXXXXXXXX`を解釈します。未知escapeは`E219`、不完全hex、surrogate、`U+10FFFF`超過は
`E220`です。

`r"..."`はすべてのbackslashを保持する1行Raw Stringです。closing quote自体は含められません。
triple quoteの複数行stringはこのpreviewには含みません。
