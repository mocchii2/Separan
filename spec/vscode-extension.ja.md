# VS Code拡張とLanguage Server

状態: **v0.5 human comprehension tooling実装済み。**

公式拡張はlanguage ID `separan`と`.sep`を担当します。TextMate scopeではlabelを
variableと分離し、Semantic Tokenではソースを書き換えずに推論済み公開型を付与します。

## 実装済みeditor core

- `#`／`##` comment、Raw／escape string、label、tagのsyntax highlight、
  quote／bracket matching、comment toggle、auto indentation
- 独立したtop-level宣言間でerror recoveryしつつruntime parserはstrictのまま保つparser診断と、
  単純な固定bindingの型診断
- `E104`／`E105` label・block kind mismatch Quick Fix
- nested Outline、breadcrumb、label単位folding
- label／variable Hover、object member表示、secretのredact
- matching label highlight、definition、block scope限定label rename、移動command
- 内側優先・opening line付きの`:end` structural completion、tag／組み込み関数completion
- 組み込み関数signature help
- label、semantic tag、parameter、variable、property、literal、keyword、comment、operatorの
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

Semantic TagはParser連動structure metadataに含まれます。LSPは同一documentのtag completionと
`separan/verifyTagScope`を提供します。Python LSP backendはtoken単位の編集と衝突検査を行う
file横断semantic tag renameにも対応します。CLIのtag path検索はdirectoryを再帰走査できます。

## 計画中の高度な機能

Python LSP backendはworkspace logic references（直接呼び出しとimport alias）、workspaceの
call siteに基づくsignature引数型推論、Call Hierarchy、reference数CodeLensを実装済みです。
`workspace/executeCommand`の`separan.runFunction`も提供し、引数なし関数にはRun Function、
`test_*`関数にはRun Test CodeLensを表示します。実行は明示操作に限り、宣言済みuser function
だけを実行し、stdoutを返します。これらのprotocol機能は、まだpackaged VS Code extensionには
接続されていません。

semantic tag workspace treeとpackaged extensionのprovider接続は引き続き計画中です。
詳細は[Structure Explorer仕様](structure-explorer.ja.md)を参照してください。
