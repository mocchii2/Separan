# Separan Roadmap

The roadmap describes direction, not a compatibility promise.

## v0.1-alpha — executable foundation

- Python reference interpreter
- explicit block labels and structural validation
- basic types, functions, conditionals, and loops
- detailed diagnostics, AST output, examples, and basic VS Code highlighting

## v0.2 — specification and diagnostics

- implemented: versioned v0.2 alpha specification and more than 1,700 conformance tests, including an API-wide negative suite
- implemented: readable mathematics, strict statistics, base conversion, and grouped binary/octal/hexadecimal literals
- implemented: labeled data blocks, temporal values, modules, capabilities, JSON, and labeled errors
- implemented: HTTP client/server previews, process execution, regex, glob, environment, and command-line helpers
- implemented: `#`/`##` comment syntax, strict escapes, raw strings, and Function Tag metadata
- implemented: exact semantic-tag inspection and edit-scope verification
- implemented: reviewed Pico/Nano board profiles, logical pins, static capability validation,
  and portable GPIO/PWM/ADC/UART/I²C examples
- next: real Pico SDK and Arduino Core code-generation/upload adapters, followed by
  SPI, sensor, Wi-Fi, and CloudWatch examples
- next: stabilize preview APIs and strengthen parser recovery before beta

## v0.3 — language tooling

- dependency-free LSP editor core implements diagnostics, mismatch Quick Fixes,
  typed Semantic Tokens, Hover, definition, scoped label rename, completion,
  signature help, inlay hints, symbols, folding, and AST-preserving formatting
- next: project-wide function argument inference, references/test CodeLens, and
  Run Current Function; Function Tag workspace UI and cross-file rename

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
- **v0.2:** 仕様整理、主要preview API、`#`／`##` comment、Raw String、Function Tag、
  semantic scope検証、review済みPico／Nano profile、論理pin、portable Embedded sample、
  1,700件超の適合testを実装済み。次は実機SDK adapterとbeta向け安定化
- **v0.3:** LSP editor core（診断、Quick Fix、Semantic Token、Hover、definition、
  label jump／rename、completion、signature、hint、symbol、fold、formatter）は実装済み。
  次はproject全体推論、CodeLens、専用structure view
- **v0.4:** AI edit scope、structural diff、対象外blockの無変更検証、machine-readable
  identity、独立browser adapter境界を実装済み
- **v0.5:** 専用Structure Explorer、block別reads／writes／calls、Git変更状態、
  click移動、cursor scope追従を実装済み
- **v1.0:** 仕様固定、互換性方針、Python Reference Implementation
