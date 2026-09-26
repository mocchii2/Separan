# Separan — Language Support for VS Code

[![Visual Studio Marketplace](https://img.shields.io/visual-studio-marketplace/v/separan.separan-language?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=separan.separan-language)

<p align="center">
  <img src="https://raw.githubusercontent.com/mocchii2/Separan/main/logo/separan_logo.png" alt="Separan" width="640">
</p>

**The complete Visual Studio Code environment for Separan 1.0.**

Write, understand, run, and review label-structured Separan programs with rich
editor support that works locally—without a separate language-server process.

```separan
SEP:main
if user.active :active_user
    message = "Hello, " + user.name
    print message
endif:active_user
END_SEP:main
```

Named boundaries make control flow readable to humans and verifiable by tools.
The extension understands those boundaries across an entire workspace and adds
the navigation, analysis, refactoring, execution, and review tools expected from
a modern language environment.

## Everything needed for Separan development

### Intelligent editing

- Completion and signature help for **all 504 built-in functions**
- Hover documentation, go to definition, references, workspace symbols, and Outline
- Local type inference and inlay hints for values, lists, calls, imports, and return unions
- Scope-safe rename for local variables, functions, labels, and semantic tags
- Automatic labeled closers, structural formatting, snippets, and Unicode labels

### Multi-file projects

- Import-aware completion, hover, signatures, definitions, references, and rename
- Correct isolation of same-named functions in different modules
- Automatic relative-import updates when `.sep` files are moved or renamed
- Cross-file label and semantic-tag navigation from dedicated Explorer views
- Call Hierarchy and CodeLens for callers, callees, references, tests, and runnable functions

### Diagnostics and Quick Fixes

- Immediate structural diagnostics while typing
- Native `separan --check` diagnostics in the Problems panel after saving
- Detection of missing or cyclic imports, duplicate declarations, unknown calls,
  invalid arguments, type mismatches, unreachable code, and unused symbols
- Quick Fixes for mismatched closing labels, unused imports, undefined functions,
  and missing module files

### Run, test, and review

- Run the current file or a zero-argument function in the integrated terminal
- Discover and run every zero-argument `test_` function in a file
- Inspect labeled structure, reads, writes, calls, and Git changes
- View structural diffs and verify that an AI edit stayed inside an approved label
- Configure the native executable, arguments, and environment per workspace

## Why labels matter

Separan gives important structures an explicit name at both boundaries:

```separan
SEP:process_payment
if payment.valid :approved_payment
    charge(payment.amount)
    write_audit_log(payment)
endif:approved_payment
END_SEP:process_payment
```

Names such as `:approved_payment`, `:write_audit_log`, and `:retry_connection`
expose intent directly in source code. Readers can identify a block and its exact
extent without reconstructing indentation or counting brackets. The extension
uses the same identity for navigation, diagnostics, structural diffs, and
AI edit-scope verification.

Separan is designed for code that humans must understand and take responsibility
for—even when AI helped write it.

## 🚀 Quick Start

### 1. Install the VS Code extension

```bash
code --install-extension separan.separan-language
```

### 2. Install the native Separan runtime

Build or install the native executable and make `separan` available on PATH.
You can also set its absolute path in `separan.executablePath`.

### 3. Create a `.sep` file

```separan
SEP:main
print "Hello from Separan"
END_SEP:main
```

### 4. Verify AI Changes

Write a labeled edit scope:

```separan
SEP:process_payment
if true :payment_approved
  amount = get_amount()
  charge_card(amount)
  log_transaction()
endif:payment_approved
END_SEP:process_payment
```

Right-click inside `:payment_approved` → **"Verify AI Edit Scope Against HEAD"**

The extension checks: ✅ Did AI only change inside this label?

## 📋 Commands

| Command | Shortcut | Purpose |
|---------|----------|---------|
| Separan: Run File | - | Execute `.sep` file |
| Separan: Check Current File | - | Save and parse-check the active `.sep` file |
| Separan: Diagnose Runtime | - | Verify the selected native executable and show its help output |
| Separan: Run Current Function | - | Run the zero-argument function under the cursor through a temporary native wrapper |
| Separan: Run Tests in Current File | - | Run every zero-argument function whose name begins with `test_` |
| Separan: Go to Matching Label | Ctrl+Shift+] | Jump to closing label |
| Separan: Go to Label | - | Browse all labeled blocks |
| Separan: Copy AI Edit Scope | - | Copy scope instruction for AI |
| **Separan: Verify AI Edit Scope Against HEAD** | - | **Verify AI stayed in scope** |
| **Separan: Show Structural Diff** | - | **See structural changes** |

## 🌳 Structure Explorer

Open the Separan icon in the Activity Bar to see the active file as a checked,
navigable structure:

```text
SEP:main
└─ :active_user              if • modified
   ├─ Reads (1)
   │  └─ user.active
   ├─ Writes (1)
   │  └─ message
   └─ Calls (1)
      └─ notify
```

The tree follows the cursor and opens a block when clicked. It shows only
direct syntactic reads, writes, and calls for each block, without executing the
program. Git-backed files also show `added`, `modified`, and removed structures
compared with `HEAD`.

## ⚙️ Configuration

```json
{
  "separan.executablePath": "separan",   // Native Separan executable
  "separan.runtimeArguments": [],         // Arguments before source/--check
  "separan.environment": {},              // Extra process environment variables
  "separan.autoCloseLabels": true,        // Auto-complete block closers
  "separan.inlayHints.types": true        // Lightweight local type hints
}
```

Run and check commands use VS Code process tasks. They start
in the active file's workspace folder, appear in the integrated terminal, and
use the configured native executable, arguments, and environment without shell interpolation.

## 🔐 Use Cases

**Useful where review boundaries matter:**
- 💰 **Financial Systems** - Every transaction block labeled and verified
- 🔒 **Security Code** - Auth blocks verified automatically
- 🏥 **Healthcare** - Scope-focused review for sensitive code
- 🌐 **Infrastructure** - Cloud automation you can audit

**Key advantage:** When your AI writes code, you get parser-backed evidence of
whether it modified anything outside the approved scope. This assists review;
it does not by itself establish regulatory compliance.

## 📚 Learn More

- [Separan Philosophy](https://github.com/mocchii2/Separan/blob/main/docs/philosophy.md)
- [Language Specification](https://github.com/mocchii2/Separan/blob/main/spec/README.md)
- [Examples](https://github.com/mocchii2/Separan/tree/main/examples)
- [Reference Implementation](https://github.com/mocchii2/Separan)

## 📝 Requirements

- VS Code 1.75.0 or later
- Native Separan executable available on PATH or configured with `separan.executablePath`
- Git (for Structural Diff feature)

## 🏷️ About Labels

Every block in Separan has an explicit name:

```separan
if condition :my_check        ← opening label
  do_something()
endif:my_check                ← must match!

while running :main_loop      ← opening label
  process()
endwhile:main_loop            ← must match!

SEP:authenticate             ← the named logic boundary is the structure identity
  verify_credentials()
END_SEP:authenticate         ← must match!
```

This is not just style—it's enforced by the language. Mismatches are caught immediately.

## 💡 Pro Tips

1. **Use descriptive labels** - `:payment_scope` is better than `:p1`
2. **Nested labels work** - Each block gets its own identity
3. **Japanese labels OK** - Use `:認証チェック` if you prefer
4. **Verify often** - Run "Verify AI Edit Scope" before committing
5. **Tag related functions** - Use `@notification` when semantic scope crosses block/file boundaries

## 🐛 Issues & Feedback

[Report issues on GitHub](https://github.com/mocchii2/Separan/issues)

[Install from the Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=separan.separan-language)

---

**This v0.6 extension works with the Separan v0.2-alpha language. Structure
Explorer, structural diff, and AI edit-scope verification are implemented.**
