# Structural AI workflows v0.4

Status: **implemented preview**. This tooling does not change v0.1 language
semantics; it compares parsed AST structure.

## Block identity

Every named structure receives a hierarchical identity. Sibling occurrences
are numbered so repeated labels remain addressable:

```text
function:main#1/if:active_user#1
```

`inspect` emits the identity, parent identity, kind, label, source location,
and SHA-256 fingerprints using the versioned `separan.structure.v1` JSON
schema. Positions, indentation, blank lines, and comments are excluded from
the fingerprint.

```console
separan-structure inspect app.sep --json
```

## Structural diff

```console
separan-structure diff app.before.sep app.after.sep
separan-structure diff app.before.sep app.after.sep --json
```

A block's own fingerprint replaces nested named blocks with identity markers.
Consequently, editing `if:active_user` marks that block as modified without
falsely marking its containing function. Adding, removing, renaming, or
reordering a child boundary is a change to its parent structure.

## AI edit-scope verification

```console
separan-structure verify app.before.sep app.after.sep --allow active_user
separan-structure verify app.before.sep app.after.sep \
  --allow function:main/if:active_user --json
```

Changes to an allowed block and its descendants pass. Any changed AST outside
that subtree fails with exit code 1. A requested boundary may not be removed,
renamed, or moved. A short label is accepted only when it uniquely identifies
one block; otherwise `S402` requires a hierarchical path.

Exit code 0 means verified, 1 means a scope violation, and 2 means invalid
source, an unknown/ambiguous scope, or an I/O failure. JSON output is intended
for CI, review bots, and editor integrations.

The VS Code v0.4 extension exposes **Show Structural Diff Against HEAD** and
**Verify AI Edit Scope Against HEAD**. It reads the baseline with direct
`git show` argument execution and sends source text to the language server's
parser-backed review requests.
