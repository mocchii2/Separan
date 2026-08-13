# Separan for VS Code

[![Visual Studio Marketplace](https://img.shields.io/visual-studio-marketplace/v/separan.separan-language?label=VS%20Code%20Marketplace)](https://marketplace.visualstudio.com/items?itemName=separan.separan-language)

<p align="center">
  <img src="images/icon.png" alt="Separan mark" width="128">
</p>

**AI-generated code verification powered by explicit labels**

Separan is a language designed so that code written by AI can be verified by humans. This VS Code extension makes that verification **instant and automatic**.

## 🎯 Why Separan?

When AI writes code, humans need to verify it. Traditional languages make this hard:

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

## ✨ Features

- **🔍 AI Edit Scope Verification** - Verify AI stayed inside a labeled block
- **📊 Structural Diff** - See *what changed structurally*, not just textually
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

Separan is not on PyPI yet. Install the current reference implementation from
GitHub:

```bash
git clone https://github.com/mocchii2/Separan.git
python -m pip install -e Separan
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

**This v0.4 extension works with the Separan v0.1-alpha language. Structural
diff and AI edit-scope verification are implemented.**
