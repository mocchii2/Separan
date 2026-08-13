# Separan for VS Code

<p align="center">
  <img src="images/icon.png" alt="Separan mark" width="128">
</p>

This experimental extension recognizes `.sep` files and highlights Separan
keywords, strings, numbers, comments, function names, and block labels using a
TextMate grammar. Its v0.3 language-server preview also provides live parser
diagnostics, a labeled-block outline, and folding ranges.
NFC-normalized Unicode block labels, including Japanese labels, are highlighted
and preserved in the outline.

The extension icon is a small-size derivative of the official Separan mark;
the unchanged brand originals remain in the repository's `logo/` directory.

For local development, run `npm install` in this directory, install Separan into
the selected Python environment, then copy or link this directory into the VS
Code extensions directory and reload the editor. Set `separan.pythonPath` when
VS Code should use a Python executable other than `python`. Semantic variable-type
colors and matching-label navigation/rename remain planned for v0.3.

This extension is part of Separan v0.1-alpha and has not been published to the
VS Code Marketplace.
