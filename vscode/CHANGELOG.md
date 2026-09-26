# Changelog

## Unreleased

## [1.1.0] - 2026-09-26

- Renames user-facing function terminology to SEP and logic terminology while
  preserving the existing command identifiers for compatibility.

## [1.0.1] - 2026-09-26

- Refreshes the Marketplace introduction for the complete Separan 1.0 editor,
  project, diagnostics, execution, and review workflow.

## [1.0.0] - 2026-09-26

### First stable release

- Updates import paths automatically when `.sep` files are renamed or moved.
- Validates runtime-supported named arguments without counting them as positional arguments.
- Merges inferred return types across branches, including `EMPTY` unions.
- Diagnoses duplicate and unused functions, unused variables, and unreachable code.
- Adds Quick Fixes for mismatched closing labels, unused imports, undefined functions,
  and missing imported module files.
- Adds Windows and Linux Extension Host CI, VSIX packaging, and package-content checks.
- Refines signatures and inferred return types for commonly used numeric, string,
  collection, date/time, random, object, and file built-ins.
- Keeps local-variable definition, references, and rename scoped to the containing
  function when another function shadows the same name.
- Finds label references and applies label rename across workspace `.sep` documents.
- Preserves list element types through immutable list operations and infers element
  types for `first`, `last`, and `random_pick`.
- Refines bytes, regex, environment, process, cryptography, and every error-constructor signature.
- Refines database, YAML, XML, and mail signatures and return types, including
  optional named arguments and `EMPTY` result unions.
- Completes user-facing parameter names and return types for HTTP client/server,
  cookies, authentication, sorting, and remaining temporal built-ins.
- Adds a full-catalog regression assertion preventing `arg1`-style parameters
  from returning to any of the 504 completion entries.
- Expands the Extension Host regression suite to 17 tests.
- Keeps references and rename for same-named functions isolated to the defining
  module and files that explicitly import it.

- Adds **Check Current File** to run the parser check from the editor title,
  command palette, or status bar.
- Adds **Diagnose Runtime** for native executable setup and recovery.
- Runs files and checks as VS Code process tasks in the
  active workspace folder.
- Adds configurable native executable arguments and process environment.
- Shows Run and Check actions in the status bar while a Separan file is active.
- Adds snippets for functions, main, labeled control flow, object/list blocks,
  try/catch, and HTTP routes.
- Removes the Python Language Server and Python runtime dependency. Structure
  browsing, structural diff, and scope verification now run inside the extension.
- Publishes immediate label-boundary diagnostics while editing and native
  `separan --check` E-code diagnostics to the Problems view after saving.
- Adds extension-local completion, hover, definition, reference, label/function rename,
  and document symbol providers without starting a language server.
- Adds local-function and common built-in signature help plus workspace-wide
  Separan symbol search.
- Adds lightweight inlay type hints for literals and common built-in calls.
- Adds Call Hierarchy, function reference-count CodeLens, semantic-tag workspace
  browsing and cross-file rename.
- Adds native execution CodeLens for zero-argument functions and `test_`
  functions using automatically removed temporary wrappers.
- Adds **Run Tests in Current File** for all zero-argument `test_` functions.
- Completes local completion and signature metadata for all 504 registered built-ins.
- Resolves aliased imports for member completion, signature help, hover,
  definitions, and inferred return types across `.sep` files.
- Resolves imported references and rename edits by alias and target file, and
  infers returns through forward function calls and local assignments.
- Adds real VS Code Extension Host regression tests for local providers,
  semantic-tag rename, the built-in catalog, imports, and type hints.
- Diagnoses missing imports, duplicate aliases, unknown imported functions,
  incompatible assignments, and invalid built-in argument counts.
- Infers homogeneous list element types, typed parameters, comparisons, and
  simple arithmetic, and tests Call Hierarchy, CodeLens, and workspace symbols.
- Resolves imported calls in both directions in Call Hierarchy without mixing
  same-named functions from unrelated modules.
- Adds a local document formatter for structure-preserving indentation and an
  Extension Host formatting regression test.
- Adds Extension Host task tests for Run File, Check Current File, Run Current
  Function, and Run Tests, including wrapper contents and temporary-file cleanup.
- Restricts automatic closer insertion to a single interactive newline so
  formatting and other whole-document edits cannot trigger competing edits.

## [0.9.8] - 2026-09-18

### Marketplace release alignment

- Updated the extension README and metadata to match the canonical `SEP` / `END_SEP` block syntax.
- Kept legacy function syntax only as compatibility support while presenting the current language identity clearly.
- Verified the extension grammar and public example snippets against the current spec.
- Bumped the Marketplace package metadata to the current GitHub-facing release version.

## [0.9.7] - 2026-09-18

### Marketplace alignment

- Updated the extension README and metadata to match the canonical `SEP` / `END_SEP` block syntax.
- Kept legacy function syntax only as compatibility support while presenting the current language identity clearly.
- Verified the extension grammar and public example snippets against the current spec.

## [0.9.6] - 2026-08-16

### Local network service preview

- Highlights Wi-Fi AP, IPv4 DHCP-server, and simple DNS-server APIs.
- Adds LSP signatures and inferred types for AP status and DHCP/DNS service handles.

## [0.9.5] - 2026-08-16

### Network address configuration

- Highlights DHCP, static-address, link-local, lease inspection, and address-wait APIs.
- Adds precise LSP signatures and inferred result types for the common Ethernet/Wi-Fi IP layer.

## [0.9.4] - 2026-08-16

### Pico firmware workflow

- Adds explicit Pico/Pico 2 build and project-generation commands for the active `.sep` file.
- Uses the same Separan CLI pipeline as terminal builds; board selection remains visible and explicit.

## [0.9.3] - 2026-08-15

### Native network API preview

- Highlights and completes strict IP address, interface inspection, DNS, TCP,
  UDP, Ethernet, and Wi-Fi status APIs.
- Adds signatures and inferred public types for network values and operations.

## [0.9.2] - 2026-08-15

### Portable embedded examples

- Documents one-source Blink builds across Raspberry Pi Pico and Arduino Nano targets.
- Links the official GPIO, PWM, ADC, UART, and I²C portable example set.

## [0.9.1] - 2026-08-15

### Embedded board profile preview

- Highlights the reserved `pin` namespace and embedded hardware APIs.
- Completes reviewed logical pin names for a source-selected Tier 1 board and
  shows backend identity, physical position, voltage, and capabilities on hover.

## [0.9.0] - 2026-08-15

### YAML and XML structured data

- Highlights strict YAML conversion, validation, multi-document, and file APIs.
- Highlights the safe XML document model, explicit element/attribute/namespace
  operations, simple path search, escaping, and typed YAML/XML errors.

## [0.8.0] - 2026-08-15

### Provider-independent mail APIs

- Highlights readable mail message, address, recipient, body, attachment,
  SMTP/SES sender, and send-result APIs.
- Highlights the redacted `secret_from_environment` boundary and typed mail
  error hierarchy.

## [0.7.1] - 2026-08-15

### Safe cryptography API highlighting

- Highlights readable SHA-2/SHA-3, HMAC, Base64, hexadecimal, Argon2id, and
  authenticated-encryption built-ins.
- Highlights `crypto_error`, `crypto_authentication_error`, and the readable
  `secure_random_number` alias.

## [0.7.0] - 2026-08-15

### Readable mathematics

- Highlights the expanded readable mathematics, statistics, and base-conversion APIs.
- Highlights binary, octal, hexadecimal, and underscore-grouped number literals.

## [0.6.1] - 2026-08-15

### Structural completion reliability

- Automatically opens completion when a standalone `:end` trigger is fully typed.
- Keeps the LSP-provided innermost-first closers and replaces the complete `:end` trigger on selection.

## [0.6.0] - 2026-08-15

### Semantic identity and symbol cleanup

- Replaced legacy `:`/`::label` comments with `#`/`##label` comments.
- Added semantic tag highlighting, completion, rename, and Structure Explorer metadata.
- Added `:end` completion with innermost-first valid closers and opening lines.
- Added strict Unicode escapes and `r"..."` raw strings.
- Added parser-backed semantic tag scope inspection and verification.

All notable changes to the Separan VS Code extension will be documented in this file.

## [0.5.4] - 2026-08-14

### Marketplace presentation

- Fixed the Separan mark URL in the Marketplace Overview so it points to the
  published `vscode/images/icon.png` asset.

## [0.5.0] - 2026-08-14

### Human Comprehension Tooling

- Added a dedicated Structure Explorer in the Activity Bar.
- Shows the parser-backed hierarchy and direct parameters, reads, writes, and
  calls for every named block without executing code.
- Shows `added` and `modified` structures against Git `HEAD`, plus a separate
  removed-structure review group.
- Added click-to-reveal navigation, cursor scope tracking, and manual refresh.
- Added the versioned `separan.document-structure.v1` LSP response schema.

## [0.4.3] - 2026-08-13

### Three-second Marketplace overview

- Added an immediate Separan label example at the top of the Marketplace page.
- Made syntax highlighting, label-aware structure, `.sep` support, and the
  GitHub repository visible before the detailed introduction.
- Explained how the same label helps human understanding and tool verification.

## [0.4.2] - 2026-08-13

### Human-readable AI-generated code

- Reframed the extension around helping humans understand AI-written code,
  alongside verifying its edit scope.
- Added clearer examples of labels as checked statements of intent.
- Corrected the runtime installation instructions and language examples.
- Added reproducible Marketplace publishing with version checks and license
  notices.

## [0.4.0] - 2026-08-13

### Major Release: AI Edit Scope Verification

This release focuses on **AI-generated code review capabilities**. The core feature: automatically verify that AI stayed inside labeled edit scopes.

### 🎯 Added

#### AI Code Review Features
- **AI Edit Scope Verification** - Verify that code changes stay within a labeled block
  - Right-click on a label → "Verify AI Edit Scope Against HEAD"
  - Get instant pass/fail confirmation with violation details
- **Structural Diff** - Compare structural changes against Git HEAD
  - See what changed *structurally*, not just textually
  - Useful for detecting unexpected structural modifications
- **Copy AI Edit Scope** - Generate AI instructions from labeled blocks
  - Right-click label → "Copy AI Edit Scope"
  - Copies a full identity such as `Modify only Separan scope SEP:main#1/if:payment_verification#1`

#### Navigation & Editing
- **Go to Matching Label** - Jump between opening and closing labels
  - Keyboard shortcut: `Ctrl+Shift+]`
  - Works across nested labels
- **Quick Label Browser** - Navigate all labeled blocks in file
  - Command: "Separan: Go to Label"
  - Shows hierarchical structure
- **Auto-Close Labels** - Automatically complete labeled block closers
  - When you type an opening label, the closer is auto-inserted
  - Controlled by `separan.autoCloseLabels` setting

#### Language Features
- **Language Server Protocol (LSP)** - Full LSP support
  - Live diagnostics (label mismatches, type errors, scope violations)
  - Hover information with type details
  - Go to Definition for functions and labels
  - Scoped label rename (safely rename labels across blocks)
  - Symbol completion and signature help
  - Outline view with breadcrumbs
  - Code folding by labeled blocks
  - Safe formatting preserving label structure
- **Semantic Tokens** - Advanced syntax highlighting
  - Precision highlighting for keywords, labels, functions, types
  - Theme-aware coloring
- **Type Inlay Hints** - Display inferred types
  - Show types after variable assignments
  - Controlled by `separan.inlayHints.types` setting
- **Japanese Label Support** - Full Unicode support
  - Labeled blocks can use Japanese (e.g., `:認証チェック`)
  - NFC-normalized for consistency
  - Displayed correctly in outline and navigation

#### Debugging
- **Show AST** - Print Abstract Syntax Tree
  - Command: "Separan: Show AST"
  - Useful for debugging parser issues
- **Run File** - Execute `.sep` files directly
  - Command: "Separan: Run File"
  - Output appears in terminal
- **Run Tests** - Execute Separan test suite
  - Command: "Separan: Run Tests"
  - Verify interpreter stability

### ⚙️ Configuration

New configuration options:
- `separan.pythonPath` (string, default: "python")
  - Path to Python executable running Separan LSP server
- `separan.autoCloseLabels` (boolean, default: true)
  - Auto-complete labeled block closers when you press Enter
- `separan.inlayHints.types` (boolean, default: true)
  - Display inferred type hints inline

### 🎨 UI/UX

- Context menu integration for all major commands
- Play button in editor toolbar for "Run File"
- Clear output formatting for Structural Diff and verification results
- Unified "Separan Review" output panel for audit reports

### 📋 Known Limitations

- **Requires Separan v0.1-alpha or later** installed and accessible via `python -m separan`
- **Git support** requires Git worktree (for Structural Diff and Scope Verification)
- **LSP server** requires Python 3.10+
- Matching label highlighting depends on label being in scope

### 🔧 Dependencies

- VS Code 1.75.0+
- Python 3.10+
- Separan v0.1-alpha
- `vscode-languageclient` 9.0.1

### 📝 Notes

- Extension works with Separan v0.1-alpha language specification
- LSP implementation provides v0.4 feature set
- v0.4 structural diff and AI edit-scope verification are implemented
- Japanese and other Unicode labels fully supported

---

## [0.1.0] - Early Preview

Initial release with basic TextMate grammar support for syntax highlighting.
