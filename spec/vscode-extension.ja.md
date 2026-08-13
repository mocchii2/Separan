# VS Code拡張とLanguage Server

状態: **v0.1 editor core実装済み。高度な構造toolingは計画中。**

公式拡張はlanguage ID `separan`と`.sep`を担当します。TextMate scopeではlabelを
variableと分離し、Semantic Tokenではソースを書き換えずに推論済み公開型を付与します。

## 実装済みeditor core

- syntax highlight、quote／bracket matching、comment toggle、auto indentation
- parser診断と単純な固定bindingの型診断
- `E104`／`E105` label・block kind mismatch Quick Fix
- nested Outline、breadcrumb、label単位folding
- label／variable Hover、object member表示、secretのredact
- matching label highlight、definition、block scope限定label rename、移動command
- open block closer、label名、組み込み関数completion
- 組み込み関数signature help
- label、function、parameter、variable、property、literal、keyword、comment、operatorの
  Semantic Tokenと公開型modifier
- 任意設定の型Inlay Hint
- 整形前後の構造AST一致を適合testで要求するformatter
- Run File、Run Tests、Show AST、Go to Label、Go to Matching Label、
  Copy AI Edit Scope command

`separan.autoCloseLabels`でlabel closer自動挿入、`separan.inlayHints.types`で型hint、
`separan.pythonPath`でLSPと実行commandが使うPythonを設定します。

## 安全性とscope規則

control label renameは同名文字列の一括置換ではなく、選択した解析済みblockだけを変更します。
function、object、list、error宣言名はprogram bindingも兼ねるため、v0.1では不完全な
labelだけのrenameを拒否します。
secret Hoverは値を一切含みません。formatterが変更できるのは装飾的indentだけで、構造ASTを
保存しなければなりません。static解析はprogramを実行しません。

## 計画中の高度な機能

program全体の関数引数推論、参照／test CodeLens、専用structure sidebar、
Run Current Function、structural diff、AI edit scope検証は計画中です。安定したproject indexや
実行／編集検証protocolを必要とするため、v0.1の保証機能とはしません。
