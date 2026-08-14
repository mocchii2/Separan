# 構造AI workflow v0.4

状態: **preview実装済み**。このtoolingはv0.1の言語意味論を変更せず、parse済みASTを
比較します。

## block identity

名前付き構造には階層identityを付与します。同じlabelを繰り返しても指定できるよう、
sibling occurrenceには番号が付きます。

```text
function:main#1/if:active_user#1
```

`inspect`はidentity、親identity、kind、label、ソース位置、SHA-256 fingerprintを、
function tag、SHA-256 fingerprintをversion付き`separan.structure.v2` JSON schemaで出力します。位置、indent、空行、commentは
fingerprintから除外されます。

```console
separan-structure inspect app.sep --json
```

## structural diff

```console
separan-structure diff app.before.sep app.after.sep
separan-structure diff app.before.sep app.after.sep --json
```

block自身のfingerprintでは、内側の名前付きblockをidentity markerへ置き換えます。
このため`if:active_user`内の変更で外側functionまで変更扱いになりません。子block境界の
追加、削除、改名、順序変更は親構造の変更です。

## AI edit scope検証

```console
separan-structure verify app.before.sep app.after.sep --allow active_user
separan-structure verify app.before.sep app.after.sep \
  --allow function:main/if:active_user --json
```

許可blockとその子孫だけの変更はPASSし、それ以外のAST変更はexit code 1でFAILします。
許可境界自体の削除、改名、移動は禁止です。短いlabelは一意な場合だけ利用でき、同名blockが
複数ある場合は`S402`が階層pathを要求します。

exit code 0は検証成功、1はscope違反、2はソース・scope指定・I/Oのエラーです。JSON出力は
CI、review bot、editor連携で利用できます。

VS Code v0.4拡張には **Show Structural Diff Against HEAD** と
**Verify AI Edit Scope Against HEAD** があります。baselineは引数配列による直接`git show`で
取得し、ソース本文をLanguage ServerのParser連動review requestへ渡します。

## Semantic Tag Scope

Function先頭metadataのtagをfileまたはworkspaceから完全一致で検索できます。

```console
separan-structure inspect . --tag notification
separan-structure inspect src --tag notification --json
```

離れた複数Functionを同じsemantic編集範囲として検証できます。

```console
separan-structure verify app.before.sep app.after.sep --allow-tag notification
```

許可Function集合はbefore ASTから確定します。そのFunction内だけの変更はPASSし、外側の変更、
Function境界の削除、許可tagの削除はFAILします。初期queryは単一tagの完全一致のみで、名前の
推測やAND／OR queryは行いません。
