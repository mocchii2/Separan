# Separan — Language Support for VS Code

[![Visual Studio Marketplace](https://img.shields.io/visual-studio-marketplace/v/separan.separan-language?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=separan.separan-language)

![Separan mark](https://github.com/mocchii2/Separan/raw/HEAD/images/icon.png)

**Make AI-written code understandable and verifiable to humans.**

Language support for the label-structured Separan programming language.

## Separan at a glance

- **Syntax highlighting** for keywords, values, functions, types, and labels
- **Label-aware structure** with diagnostics, navigation, Outline, folding, and rename
- **`.sep` file support** in Visual Studio Code
- **[GitHub repository](https://github.com/mocchii2/Separan)** with the interpreter, specification, and examples

```separan
if user.active :active_user
    print "active"
endif:active_user
```

The label names the structure and its exact boundary. Even before using the
tooling, a reader can see that this block handles an active user. The extension
then checks that both endpoints agree and lets reviewers navigate or verify the
same named scope.

AI can generate code quickly. Humans still have to understand it, review it,
and take responsibility for it. Separan gives every important structure an
explicit, checked name, and this extension turns those names into navigation,
explanations, structural diffs, and automatic scope verification.

Labels such as `:validate_payment`, `:write_audit_log`, and
`:retry_connection` expose intent directly in the code. Reviewers can see what
a block is for and where it ends without reconstructing indentation or counting
brackets. Verification then answers the second question: **did the AI change
only the structure it was asked to change?**

## 🎯 Why Separan?

When AI writes code, humans first need to understand it and then verify it.
Traditional languages make both tasks harder:

```python
# ❌ Which code did the AI actually change?
if check_payment():  # was this modified?
    process()       # or this?
    log()          # or this?
```

Separan makes verification explicit:

```separan
if check_payment() :ai_payment_scope
process()
log()
endif:ai_payment_scope
```

Now you can ask: **"Did AI only modify inside `:ai_payment_scope`?"** and the extension verifies it automatically.

The label also tells a human what the block means before any tool is opened.
Separan treats human comprehension and machine verification as the same
structural problem.

## ✨ Features

- **🔍 AI Edit Scope Verification** - Verify AI stayed inside a labeled block
- **📊 Structural Diff** - See *what changed structurally*, not just textually
- **🧭 Human-Readable Structure** - Make generated control flow explain its intent
- **🌳 Structure Explorer** - Browse block hierarchy, reads, writes, calls, and Git changes
- **🏷️ Label Navigation** - Jump between matching labels instantly (Ctrl+Shift+])
- **⚡ Live Diagnostics** - Catch label mismatches, type errors, scope violations instantly
- **🤖 AI-Verifiable Syntax** - No implicit conversions, no indentation tricks
- **🌍 Unicode Labels** - Full support for Japanese and other Unicode labels
- **💡 Type Hints** - Inline type inference
- **🎨 Rich Syntax Highlighting** - Semantic tokens for precision highlighting

## 🚀 Quick Start

### 1. Install the VS Code extension

```bash
code --install-extension separan.separan-language
```

### 2. Install the Separan reference runtime

Install the Separan reference implementation from PyPI:

```bash
python -m pip install separan-lang
```

### 3. Create a `.sep` file

```separan
function:main
print "Hello from Separan"
end_function:main
```

### 4. Verify AI Changes

Write a labeled edit scope:

```separan
function:process_payment
if true :payment_approved
  amount = get_amount()
  charge_card(amount)
  log_transaction()
endif:payment_approved
end_function:process_payment
```

Right-click inside `:payment_approved` → **"Verify AI Edit Scope Against HEAD"**

The extension checks: ✅ Did AI only change inside this label?

## 📋 Commands

| Command | Shortcut | Purpose |
|---------|----------|---------|
| Separan: Run File | - | Execute `.sep` file |
| Separan: Go to Matching Label | Ctrl+Shift+] | Jump to closing label |
| Separan: Go to Label | - | Browse all labeled blocks |
| Separan: Copy AI Edit Scope | - | Copy scope instruction for AI |
| **Separan: Verify AI Edit Scope Against HEAD** | - | **Verify AI stayed in scope** |
| **Separan: Show Structural Diff** | - | **See structural changes** |
| Separan: Show AST | - | Debug: print syntax tree |
| Separan: Run Tests | - | Run language tests |

## 🌳 Structure Explorer

Open the Separan icon in the Activity Bar to see the active file as a checked,
navigable structure:

```text
main                         function
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
  "separan.pythonPath": "python",        // Python executable
  "separan.autoCloseLabels": true,       // Auto-complete block closers
  "separan.inlayHints.types": true       // Show inferred types
}
```

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
- Python 3.10 or later (with `separan` package installed)
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

function:authenticate         ← function name is its structure identity
  verify_credentials()
end_function:authenticate     ← must match!
```

This is not just style—it's enforced by the language. Mismatches are caught immediately.

## 💡 Pro Tips

1. **Use descriptive labels** - `:payment_scope` is better than `:p1`
2. **Nested labels work** - Each block gets its own identity
3. **Japanese labels OK** - Use `:認証チェック` if you prefer
4. **Verify often** - Run "Verify AI Edit Scope" before committing

## 🐛 Issues & Feedback

[Report issues on GitHub](https://github.com/mocchii2/Separan/issues)

[Install from the Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=separan.separan-language)

---

**This v0.5 extension works with the Separan v0.1-alpha language. Structure
Explorer, structural diff, and AI edit-scope verification are implemented.**
