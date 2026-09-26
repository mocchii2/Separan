# Versioning and Compatibility Policy

This policy separates the language specification revision from the Python package release version. The package release version is recorded in `pyproject.toml`; the language revision is recorded in the specification heading. They may advance independently, but release notes must identify both when a change affects language behavior.

## Before 1.0

Separan is pre-stable software. A `0.y` release may include documented breaking changes to syntax, runtime behavior, built-ins, diagnostics, or tooling. Patch releases should normally be limited to compatible fixes, but preview and experimental APIs may still change when necessary. Such changes must be called out in the release notes and the affected specification must be updated.

An API or feature explicitly marked **preview** or **experimental** has no compatibility guarantee before it is promoted to stable. The core language specification and stable standard-library behavior are the intended compatibility surface; changes to them before 1.0 must be documented and covered by conformance tests.

## From 1.0

Stable language and standard-library behavior follows semantic versioning:

- **Patch:** backward-compatible bug and security fixes; no intentional syntax or API removal.
- **Minor:** backward-compatible language, standard-library, and tooling additions; existing programs retain their documented meaning.
- **Major:** breaking changes to syntax, runtime behavior, built-ins, public error codes, or stable tool interfaces.

A stable feature is not removed or incompatibly changed without a deprecation notice and a migration path. Security fixes may require an accelerated exception, which must be documented.

## Conformance and reference implementation

The Python implementation is the normative behavioral reference. The conformance suite records observable behavior, including output, diagnostics, exit status, and side effects where applicable. Other implementations, including the independent C runtime, must pass the relevant conformance checks before being described as compatible.

Preview features are tested for regressions but are not part of the 1.0 compatibility promise until their status is changed in the specification.

## Current repository status

The Python package version is `1.0.0`. The native C runtime is an
independent implementation and is checked by the cross-implementation suite;
the current repository run collects 2,145 tests: 2,142 pass automatically and
3 external database integration tests are skipped without credentials; all
three have also been verified manually. The VS Code extension is published as
`separan-language` 1.1.0. The v1.0 core specification is frozen by
`spec/README.md`; features explicitly marked preview or experimental remain
outside the stable compatibility promise until promoted in a later release.
