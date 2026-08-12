# AI integration

Separan labels are intended to be safe, human-readable edit boundaries.

```text
Modify only the :payment_validation block.
Do not change :audit_log.
```

Because labels are syntax and AST data, future tooling can verify these
instructions instead of treating them as informal comments. Planned uses include:

- label-scoped AI edit permissions;
- structural diffs grouped by named blocks;
- confirmation that untouched labels have unchanged ASTs;
- matching-block navigation and rename;
- block ownership, history, and review policies.

AI integration must remain inspectable. A human-readable label should map to the
same structural identity seen by the parser, editor, diff tool, and AI agent.

