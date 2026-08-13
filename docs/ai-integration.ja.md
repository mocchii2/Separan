# AI連携

Separanのラベルは、人間が読める安全な編集境界として利用することを想定しています。

```text
:payment_validation ブロックだけ変更してください。
:audit_log には変更を加えないでください。
```

ラベルはコメントではなく構文およびASTデータなので、v0.4 toolingはこの指示を
お願いとして扱わず、機械的に検証します。実装済みの用途は次のとおりです。

- ラベル単位のAI編集権限
- 名前付きブロック単位の構造差分
- 対象外ラベルのASTが変化していないことの確認
- 対応ブロックへの移動と安全なrename

ブロック単位の所有者、履歴、レビューポリシーは将来の拡張です。

AI連携は人間が検証できなければなりません。人間が読むラベル、パーサーの構造ID、
エディタ、差分ツール、AIエージェントが、同じ構造を指す設計を目指します。

```console
separan-structure inspect app.sep --json
separan-structure diff before.sep after.sep
separan-structure verify before.sep after.sep --allow payment_validation
```

許可blockのsubtree外でparse済み構造が変わるとexit status 1になります。詳細は
[v0.4構造workflow仕様](../spec/structural-ai.ja.md)を参照してください。

