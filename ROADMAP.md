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

- dependency-free LSP editor core implements diagnostics, mismatch Quick Fixes,
  typed Semantic Tokens, Hover, definition, scoped label rename, completion,
  signature help, inlay hints, symbols, folding, and AST-preserving formatting
- next: project-wide function argument inference, references/test CodeLens, and
  Run Current Function

## v0.4 — structural AI workflows

- implemented: AI edit scopes enforced by hierarchical label identities
- implemented: AST-aware structural diffs that ignore decorative source changes
- implemented: verification that out-of-scope blocks remain unchanged
- implemented: versioned machine-readable block identities and review metadata
- implemented: a separate browser adapter boundary; no HTTP fallback may impersonate a browser

## v0.5 — human comprehension tooling

- implemented: a dedicated Structure Explorer with parser-backed block hierarchy
- implemented: direct reads, writes, calls, and function parameters per named block
- implemented: Git `HEAD` structural status and a removed-block review group
- implemented: click navigation and active-cursor scope tracking
- next: project-wide references, call hierarchy, test CodeLens, and function argument inference

## v1.0 — stable language

- freeze the core specification
- publish a compatibility and versioning policy
- designate the Python implementation as the reference implementation
- provide a complete conformance suite

---

## 日本語概要

- **v0.1-alpha:** 現在の処理系、ラベル検証、基本型、関数、制御構文
- **v0.2:** 仕様整理、object、時間専用型、エラー診断強化、100ケースを超える適合テスト
- **v0.3:** LSP editor core（診断、Quick Fix、Semantic Token、Hover、definition、
  label jump／rename、completion、signature、hint、symbol、fold、formatter）は実装済み。
  次はproject全体推論、CodeLens、専用structure view
- **v0.4:** AI edit scope、structural diff、対象外blockの無変更検証、machine-readable
  identity、独立browser adapter境界を実装済み
- **v0.5:** 専用Structure Explorer、block別reads／writes／calls、Git変更状態、
  click移動、cursor scope追従を実装済み
- **v1.0:** 仕様固定、互換性方針、Python Reference Implementation
