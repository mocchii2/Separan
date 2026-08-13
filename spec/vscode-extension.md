# VS Code Extension and Language Server

Status: **v0.1 editor core implemented; advanced structural tooling planned.**

The official extension owns the `separan` language ID and `.sep` extension.
TextMate scopes distinguish labels from variables, while semantic tokens add
inferred public types without changing source text.

## Implemented editor core

- syntax highlighting, quote/bracket matching, comment toggle, and indentation;
- live parser and simple fixed-binding type diagnostics;
- `E104`/`E105` label and block-kind mismatch quick fixes;
- nested Outline, breadcrumbs, and label-based folding;
- label and variable hover, including object members and redacted secrets;
- matching-label highlights, definition, block-scoped label rename, and commands;
- open-block closer, label-name, and built-in completion;
- built-in signature help;
- semantic tokens for labels, functions, parameters, variables, properties,
  literals, keywords, comments, and operators, with public-type modifiers;
- optional inferred-type inlay hints;
- a formatter whose conformance test requires identical structural AST output;
- Run File, Run Tests, Show AST, Go to Label, Go to Matching Label, and Copy AI
  Edit Scope commands.

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

## Planned advanced tooling

Whole-program argument inference, references/test CodeLens, a dedicated
structure sidebar, Run Current Function, structural diff, and AI edit-scope
verification remain planned. These require stable project-wide indexing or an
execution/edit verification protocol and are not presented as v0.1 guarantees.
