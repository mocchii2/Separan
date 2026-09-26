# Separan Roadmap

The roadmap describes direction, not a compatibility promise.

## v0.1-alpha — executable foundation

- Python reference interpreter
- explicit block labels and structural validation
- basic types, functions, conditionals, and loops
- detailed diagnostics, AST output, examples, and basic VS Code highlighting

## v0.2 — specification and diagnostics

- implemented: versioned v0.2 alpha specification and more than 1,800 conformance tests, including an API-wide negative suite
- implemented: readable mathematics, strict statistics, base conversion, and grouped binary/octal/hexadecimal literals
- implemented: labeled data blocks, temporal values, modules, capabilities, JSON, and labeled errors
- implemented: HTTP client/server previews, process execution, regex, glob, environment, and command-line helpers
- implemented: capability-separated native interface inspection, strict IP values, deterministic DNS, and bounded TCP/UDP
- implemented: `#`/`##` comment syntax, strict escapes, raw strings, and semantic tag metadata
- implemented: exact semantic-tag inspection and edit-scope verification
- implemented: reviewed Pico/Nano board profiles, logical pins, static capability validation,
  and portable GPIO/PWM/ADC/UART/I²C examples
- implemented: Pico/Pico 2 C++ generation, official Pico SDK CMake/Ninja compile,
  ELF/UF2/HEX verification, and explicit marker-checked BOOTSEL deployment
- next: Pico W CYW43 and Arduino Core firmware backends, followed by SPI, sensor,
  Wi-Fi, and CloudWatch examples
- implemented: LSP diagnostics recover across independent top-level declarations
  without changing strict runtime parsing
- next: stabilize preview APIs and strengthen recovery for malformed/incomplete
  nested structures before beta

## v0.3 — language tooling

- dependency-free LSP editor core implements diagnostics, mismatch Quick Fixes,
  typed Semantic Tokens, Hover, definition, scoped label rename, completion,
  signature help, inlay hints, symbols, folding, and AST-preserving formatting
- implemented in the Python LSP backend: workspace function references,
  imported-call argument inference, Call Hierarchy, reference/test CodeLens,
  Run Current Function, and cross-file semantic-tag rename
- next: semantic-tag workspace UI and wiring these backend requests into the
  packaged VS Code extension

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
- implemented in the Python LSP backend: project-wide references and argument
  inference, Call Hierarchy, reference/test CodeLens, and Run Current Function
- next: semantic-tag workspace UI and packaged extension integration

## v1.0 — stable language

- freeze the core specification
- implemented: publish a compatibility and versioning policy in `spec/versioning.md`
- designate the Python implementation as the reference implementation
- provide a complete conformance suite

---

## 日本語概要

- **v0.1-alpha:** 現在の処理系、ラベル検証、基本型、関数、制御構文
- **v0.2:** 仕様整理、主要preview API、`#`／`##` comment、Raw String、Semantic Tag、
  semantic scope検証、review済みPico／Nano profile、論理pin、portable Embedded sample、
  Pico／Pico 2のC++／SDK compile／UF2書き込み、native interface／IP／DNS／TCP／UDP、
  1,800件超の適合testとtop-level宣言単位のLSP parser recoveryを実装済み。次はPico W／Arduino
  firmware backendとnested structureのrecoveryを含むbeta向け安定化
- **v0.3:** LSP editor core（診断、Quick Fix、Semantic Token、Hover、definition、
  label jump／rename、completion、signature、hint、symbol、fold、formatter）に加え、
  Python LSP backendのworkspace function references、引数型推論、Call Hierarchy、
  reference／test CodeLens、Run Current Function、cross-file semantic tag renameを実装済み。
  次はtag workspace UIとVS Code extensionへの接続
- **v0.4:** AI edit scope、structural diff、対象外blockの無変更検証、machine-readable
  identity、独立browser adapter境界を実装済み
- **v0.5:** 専用Structure Explorer、block別reads／writes／calls、Git変更状態、
  click移動、cursor scope追従を実装済み
- **v1.0:** 互換性方針は`spec/versioning.md`に実装済み。仕様固定、Python Reference Implementation、
  完全な適合suiteは継続作業
