# VS Code拡張とLanguage Server

状態: **v0.5 human comprehension tooling実装済み。**

公式拡張はlanguage ID `separan`と`.sep`を担当します。TextMate scopeではlabelを
variableと分離し、Semantic Tokenではソースを書き換えずに推論済み公開型を付与します。

## 実装済みeditor core

- `#`／`##` comment、Raw／escape string、label、tagのsyntax highlight、
  quote／bracket matching、comment toggle、auto indentation
- parser診断と単純な固定bindingの型診断
- `E104`／`E105` label・block kind mismatch Quick Fix
- nested Outline、breadcrumb、label単位folding
- label／variable Hover、object member表示、secretのredact
- matching label highlight、definition、block scope限定label rename、移動command
- 内側優先・opening line付きの`:end` structural completion、tag／組み込み関数completion
- 組み込み関数signature help
- label、function、parameter、variable、property、literal、keyword、comment、Function Tag、operatorの
  Semantic Tokenと公開型modifier
- 任意設定の型Inlay Hint
- 整形前後の構造AST一致を適合testで要求するformatter
- Run File、Run Tests、Show AST、Go to Label、Go to Matching Label、
  Copy AI Edit Scope command
- Parser連動のStructural Diff Against HEAD、AI Edit Scope Verification Against HEAD、
  階層block identity
- block階層、直接parameter／reads／writes／calls、Git構造状態、削除identityを表示する
  専用Structure Explorer
- Explorerからのclick移動とeditor cursorのscope追従

`separan.autoCloseLabels`でlabel closer自動挿入、`separan.inlayHints.types`で型hint、
`separan.pythonPath`でLSPと実行commandが使うPythonを設定します。

## 安全性とscope規則

control label renameは同名文字列の一括置換ではなく、選択した解析済みblockだけを変更します。
function、object、list、error宣言名はprogram bindingも兼ねるため、v0.1では不完全な
labelだけのrenameを拒否します。
secret Hoverは値を一切含みません。formatterが変更できるのは装飾的indentだけで、構造ASTを
保存しなければなりません。static解析はprogramを実行しません。

## 構造reviewの安全性

Git baselineはshell文字列へ埋め込まず、processへ直接引数を渡して取得します。editorは
baselineと現在の本文をLanguage Serverへ渡し、両方をparseしてから比較します。
空白・commentだけの差は無視し、選択subtree外のAST変更はFAILします。短いlabelが曖昧なら、
Copy AI Edit Scopeが出す完全pathを要求します。

Function TagはParser連動structure metadataに含まれます。LSPは同一documentのtag completion／
renameと`separan/verifyTagScope`を提供します。workspace tag treeとfile横断renameは安定した
workspace indexが必要な将来UIですが、CLIのtag path検索はdirectoryを再帰走査できます。

## 計画中の高度な機能

program全体の関数引数推論、参照／test CodeLens、call hierarchy、Run Current Functionは
計画中です。安定したproject indexを必要とするため、v0.5の保証機能とはしません。
詳細は[Structure Explorer仕様](structure-explorer.ja.md)を参照してください。
