# Separan Roadmap

The roadmap describes direction, not a compatibility promise.

## v0.1-alpha — executable foundation

- Python reference interpreter
- explicit block labels and structural validation
- basic types, functions, conditionals, and loops
- detailed diagnostics, AST output, examples, and basic VS Code highlighting

## v0.2 — specification and diagnostics

- refine and version the language specification
- add labeled `object:name` and multiline `list:name` data blocks
- stabilize the preview `datetime`, `local_datetime`, `timezone`, and `duration` types
- stabilize explicit timezone and unit-bearing Unix conversions
- add objects/lists, namespaced imports, capability-based I/O, explicit JSON conversion, and labeled errors in that order
- add a capability-gated HTTP client after named arguments, objects, and catchable errors
- add capability-gated direct process execution; keep shell execution separately gated
- add regex, deterministic capability-gated globbing, scoped environment access, and command-line helpers
- strengthen diagnostics and recovery
- grow conformance and negative tests beyond 100 cases

## v0.3 — language tooling

- Language Server Protocol implementation
- semantic tokens and inferred variable-type colors
- matching-label navigation, highlight, rename, and folding
- block hierarchy view

## v0.4 — structural AI workflows

- AI edit scopes enforced by labels
- AST-aware structural diffs
- verification that out-of-scope blocks remain unchanged
- machine-readable block identities and review metadata
- begin a separate browser automation module; never merge it into the HTTP client

## v1.0 — stable language

- freeze the core specification
- publish a compatibility and versioning policy
- designate the Python implementation as the reference implementation
- provide a complete conformance suite

---

## 日本語概要

- **v0.1-alpha:** 現在の処理系、ラベル検証、基本型、関数、制御構文
- **v0.2:** 仕様整理、object、時間専用型、エラー診断強化、100ケースを超える適合テスト
- **v0.3:** LSP、Semantic Tokens、ラベルジャンプ・rename・fold
- **v0.4:** AI edit scope、structural diff、対象外ブロックの無変更検証
- **v1.0:** 仕様固定、互換性方針、Python Reference Implementation
