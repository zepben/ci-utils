# Ubiquitous language: CI

These terms apply inside `src/zep_dev/ci/`; see [context.md](context.md).
Use them consistently in identifiers, tests, errors and documentation. Add terms
as capabilities need them, rather than defining a model for future work.

| Term | Meaning | Code or contract |
| --- | --- | --- |
| **Operation** | Repository work callable independently of the CLI, locally or in CI. An operation may check inputs or change files and external state; its command documents which. | [Context rules](context.md#rules-and-structure) |

Git commits, pull requests, snapshots and project-tool names retain their external
meanings. Development Environments terms belong to that context's
[glossary](../development_environments/language.md), not to every operation that happens to run in CI.
