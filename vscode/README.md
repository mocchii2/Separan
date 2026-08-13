# Separan for VS Code

<p align="center">
  <img src="images/icon.png" alt="Separan mark" width="128">
</p>

This experimental extension recognizes `.sep` files and keeps labels in a
dedicated TextMate and Semantic Token category. Its language server provides
live diagnostics and mismatch Quick Fixes, typed Semantic Tokens and inlay
hints, Hover, definition, scoped label rename, matching highlights, completion,
signature help, nested Outline/breadcrumbs, folding, and safe formatting.
NFC-normalized Unicode block labels, including Japanese labels, are highlighted
and preserved in the outline.

The extension icon is a small-size derivative of the official Separan mark;
the unchanged brand originals remain in the repository's `logo/` directory.

Commands include Run File, Run Tests, Show AST, Go to Label, Go to Matching
Label, and Copy AI Edit Scope. Labeled blocks can auto-close, controlled by
`separan.autoCloseLabels`; type hints use `separan.inlayHints.types`.

For local development, run `npm install` in this directory, install Separan into
the selected Python environment, then copy or link this directory into the VS
Code extensions directory and reload the editor. Set `separan.pythonPath` when
VS Code should use a Python executable other than `python`. See the complete
[editor specification](../spec/vscode-extension.md) for implemented and planned scope.

This extension is part of Separan v0.1-alpha and has not been published to the
VS Code Marketplace.
