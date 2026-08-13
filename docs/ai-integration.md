# AI integration

Separan labels are intended to be safe, human-readable edit boundaries.

```text
Modify only the :payment_validation block.
Do not change :audit_log.
```

Because labels are syntax and AST data, the v0.4 tooling verifies these
instructions instead of treating them as informal comments. Implemented uses include:

- label-scoped AI edit permissions;
- structural diffs grouped by named blocks;
- confirmation that untouched labels have unchanged ASTs;
- matching-block navigation and rename;

Block ownership, history, and review policies remain future extensions.

AI integration must remain inspectable. A human-readable label should map to the
same structural identity seen by the parser, editor, diff tool, and AI agent.

```console
separan-structure inspect app.sep --json
separan-structure diff before.sep after.sep
separan-structure verify before.sep after.sep --allow payment_validation
```

Verification exits with status 1 when any parsed structure outside the allowed
block subtree changes. See the [v0.4 structural workflow specification](../spec/structural-ai.md).

