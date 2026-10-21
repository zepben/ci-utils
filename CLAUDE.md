# ci-utils

This repository holds `zep-dev` (a Python CLI: local Kubernetes development
Environments, plus chart CI utilities) and `pipelines/` (Packer images, unrelated to
`zep-dev`). `changelog.md` records releases. Everything below is about `zep-dev/`.

## Domain model

`zep-dev` uses a small subset of Domain-Driven Design: a ubiquitous language carried
into code and tests, and an explicit bounded context.

- Read [language.md](zep-dev/docs/language.md) before naming anything. Use its
  terms in identifiers, test names, error messages and docs.
- Read [context.md](zep-dev/docs/context.md) before changing behavior. It
  lists the rules (with the test files that cover each group), the creation flow,
  which module owns what, and where to make each kind of change.
- One bounded context exists: Development Environments
  (`zep-dev/src/zep_dev/development_environments/`). Chart CI (`charts/`,
  `commands/chart/`, `commands/tools/`) is outside it and will become a separate
  context. In that code "chart" means a directory under a Helm directory. It must not
  import `development_environments` (enforced by `tests/test_architecture.py`).
- Keep external terms as they are: Distribution, and the application names EWB, EAS,
  HCS and web client.

## Rules for changes

- Test names state the rule they protect, in the ubiquitous language.
- When you add or change a term or rule, update `language.md` (terms and their code
  anchors) or `context.md` (rules and the tests that cover them) in the same change.
- A rule with no validator or test is a convention. Prefer adding the test.
- Respect the layering in `context.md`: configuration modules do no I/O,
  integrations never import `lifecycle` or CLI code, the CLI stays thin.
- Pass an explicit Environment target to every call that acts on an Environment's
  cluster or files (Kind, kubectl, Helm, Terraform). Never rely on the caller's
  Kubernetes context.

## Commands

From the repository root, with Python 3.14:

```sh
make check-zep-dev test-zep-dev
git diff --check
```

Human documentation: [README](zep-dev/README.md).
