# Versioningと互換性方針

この方針では、言語仕様revisionとPython packageのrelease versionを区別します。package release versionは`pyproject.toml`、language revisionは仕様書見出しで管理します。両者は独立して進められますが、言語動作へ影響する変更を含むrelease noteでは双方を明記します。

## 1.0以前

Separanは安定版リリース前です。`0.y` releaseでは、syntax、runtime動作、組み込み関数、診断、toolingに対する文書化されたbreaking changeを含むことがあります。patch releaseは原則として互換性を保つ修正に限定しますが、preview／experimental APIは必要に応じて変更される場合があります。変更内容はrelease noteに記し、関連する仕様と適合testを更新します。

**preview**または**experimental**と明記された機能には、安定版になるまで互換性保証がありません。コア言語仕様とstableと指定された標準libraryの動作を互換対象とし、1.0以前にこれらを変更する場合は変更を文書化し、適合testで固定します。

## 1.0以降

stableな言語と標準libraryの動作はSemantic Versioningに従います。

- **Patch:** 互換性を保つbug／security修正。意図したsyntax・API削除は含めません。
- **Minor:** 既存programの文書化された意味を保つ、後方互換な言語・標準library・toolingの追加。
- **Major:** syntax、runtime動作、組み込み関数、公開error code、stable tool interfaceのbreaking change。

stable機能を非互換に変更または削除する場合は、deprecation noticeと移行手順を事前に示します。security修正では迅速な例外対応が必要になる場合があり、その際は内容を記録します。

## 適合性とReference Implementation

Python実装を規範的な動作referenceとします。適合testは、適用可能な範囲でstdout／stderr、診断、exit status、副作用などの観測可能な動作を記録します。独立したC runtimeを含む他の実装は、互換と表記する前に該当する適合testを通過する必要があります。

preview機能もregression testの対象ですが、仕様書でstableへ変更されるまでは1.0互換保証の対象外です。
