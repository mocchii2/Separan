# Structure Explorer v0.5

状態: **editor toolingとして実装済み**。Separanの言語意味論は変更しません。

Structure Explorerは、AIが書いた`.sep` fileの構造を、人間が短時間で理解して移動できる
形にします。Parser ASTと、structural diff／AI edit scope検証と同じ階層block identityを
利用します。

各名前付きblockには次を表示します。

- 内側のfunctionとlabel付き構造
- function parameter
- function semantic tag
- そのblockが直接読む名前
- そのblockが直接書くbinding
- そのblockが直接呼ぶfunction／member function
- Git `HEAD`と比較した`added`／`modified`状態
- 別review groupにまとめた削除済みblock identity

解析は構文的で、ユーザーコードを一切実行しません。親の要約へ内側の名前付きblockの処理を
混ぜないため、statementを所有するblockごとの責任が見えます。`user.active`のようなmember
accessは`user`へ潰さず、修飾名のまま表示します。

構造を選ぶと開始位置へ移動し、editor cursorを動かすと最も内側の該当構造をtree上で選択します。
未追跡fileやGit外のfileでも階層と静的要約は利用でき、変更状態だけを省略します。

LSP request `separan/documentStructure`はversion付き
`separan.document-structure.v2` schemaを返します。安定identity path、1始まりのソース範囲、
直接のreads／writes／calls、parameter、tag、再帰childrenをeditorやreview toolから利用できます。
