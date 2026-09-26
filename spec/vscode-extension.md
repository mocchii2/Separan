# VS Code Extension and Language Server

Status: **v0.5 human comprehension tooling implemented.**

The official extension owns the `separan` language ID and `.sep` extension.
TextMate scopes distinguish labels from variables, while semantic tokens add
inferred public types without changing source text.

## Implemented editor core

- syntax highlighting for `#`/`##` comments, raw/escaped strings, labels and tags,
  plus quote/bracket matching, comment toggle, and indentation;
- live parser and simple fixed-binding type diagnostics, with LSP recovery across
  independent top-level declarations while runtime parsing remains strict;
- `E104`/`E105` label and block-kind mismatch quick fixes;
- nested Outline, breadcrumbs, and label-based folding;
- label and variable hover, including object members and redacted secrets;
- matching-label highlights, definition, block-scoped label rename, and commands;
- `:end` structural completion, with open-block closers ordered innermost first
  and annotated with opening lines; tag and built-in completion;
- built-in signature help;
- semantic tokens for labels, functions, parameters, variables, properties,
  literals, keywords, comments, semantic tags, and operators, with public-type modifiers;
- optional inferred-type inlay hints;
- a formatter whose conformance test requires identical structural AST output;
- Run File, Run Tests, Show AST, Go to Label, Go to Matching Label, and Copy AI
  Edit Scope commands;
- parser-backed Structural Diff Against HEAD and AI Edit Scope Verification
  Against HEAD commands, with hierarchical block identities.
- a dedicated Structure Explorer showing block hierarchy, direct parameters,
  reads, writes, calls, Git structural status, and removed identities;
- click-to-reveal navigation and active-cursor scope tracking in the Explorer.

`separan.autoCloseLabels` controls labeled closer insertion.
`separan.inlayHints.types` controls type hints. `separan.pythonPath` selects the
Python executable used by both the language server and run commands.

## Safety and scope rules

Control-label rename operates on the selected parsed block, not text matches
elsewhere. Function, object, list, and error declaration names also act as
program bindings, so v0.1 refuses partial label-only rename for those symbols.
Secret hover never includes the secret value. Formatting may alter decorative
indentation only and must preserve the structural AST. Static analysis never
executes the program.

## Structural review safety

Git baselines are read with direct process arguments, never interpolated into a
shell command. The editor sends the baseline and current text to the language
server; both are parsed before comparison. Whitespace/comments are ignored,
while AST changes outside the selected subtree fail verification. Ambiguous
short labels require the full path copied by Copy AI Edit Scope.

Semantic tags are included in parser-backed structure metadata. The LSP supports
same-document tag completion and `separan/verifyTagScope`. The Python LSP backend
also supports cross-file semantic-tag rename with token-based edits and collision
checks; the CLI performs recursive tag-path inspection.

## Planned advanced tooling

The Python LSP backend supports workspace logic references for direct calls
and imported aliases, signature parameter inference from workspace call sites,
Call Hierarchy, and reference-count CodeLens. It also exposes
`separan.runFunction` through `workspace/executeCommand`; Run SEP and Run
Test CodeLens are offered for zero-argument functions (`test_*` for tests).
Execution is explicit, limited to declared user functions, and returns captured
stdout. These protocol features are not yet wired into the packaged VS Code
extension.

A semantic-tag workspace tree and packaged-extension provider wiring remain
planned. See the [Structure Explorer specification](structure-explorer.md).
