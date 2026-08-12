# Python reference implementation

`reference/separan/` contains the Separan v0.1-alpha lexer, parser, AST,
interpreter, diagnostics, AST printer, and CLI. It prioritizes readable behavior
and conformance with `spec/` over optimization.

Install from the repository root with `python -m pip install -e .`, then run
`separan examples/hello.sep`.

Built-in functions live in `separan/builtins.py`. Each declaration carries its
arity and implementation, keeping dispatch and diagnostics separate from
user-defined function frames. New built-ins should remain explicit about input
types and must not introduce implicit conversion.
