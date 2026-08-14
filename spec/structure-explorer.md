# Structure Explorer v0.5

Status: **implemented editor tooling**. This feature does not change Separan
language semantics.

The Structure Explorer gives humans a compact, navigable explanation of an
AI-written `.sep` file. It uses the parser AST and the same hierarchical block
identities as structural diff and AI edit-scope verification.

For each named block it shows:

- nested functions and labeled structures;
- function parameters;
- function semantic tags;
- names directly read by that block;
- bindings directly written by that block;
- functions and member functions directly called by that block;
- `added` or `modified` state compared with Git `HEAD`;
- removed block identities in a separate review group.

The analysis is syntactic and never executes user code. A parent summary does
not absorb work performed by a nested named block; this keeps responsibility
visible at the block that owns the statements. Member access such as
`user.active` remains qualified rather than being reduced to `user`.

Selecting a structure reveals its opener. Moving the editor cursor selects the
deepest enclosing structure in the tree. Untracked files and files outside Git
still receive the full hierarchy and static summaries, only without change
status.

The LSP request `separan/documentStructure` returns the versioned
`separan.document-structure.v2` schema. It includes stable identity paths,
one-based source ranges, direct reads/writes/calls, parameters, tags, and recursive
children for editor or review-tool integrations.
