# ci-utils

This repository holds `zep-dev` (a Python CLI for local Kubernetes development
Environments, chart utilities and repository CI operations) and `pipelines/`
(pipeline images and scripts). `changelog.md` records releases. Everything below
is about `zep-dev/`.

## Domain model

`zep-dev` uses a small subset of Domain-Driven Design: context-specific language
carried into code and tests, explicit ownership, and enforced dependency boundaries.

Read the relevant context and language before changing behaviour or naming things:

| Context | Code | Rules and ownership | Language |
| --- | --- | --- | --- |
| Development Environments | `src/zep_dev/development_environments/` | [context](zep-dev/docs/development_environments/context.md) | [language](zep-dev/docs/development_environments/language.md) |
| CI | `src/zep_dev/ci/` | [context](zep-dev/docs/ci/context.md) | [language](zep-dev/docs/ci/language.md) |

- Use that context's terms in identifiers, test names, error messages and docs.
- Neither context imports the other. Shared infrastructure does not import either.
  The root CLI imports their CLI modules to register commands. These boundaries
  are enforced by `tests/test_architecture.py`.
- Existing chart commands and tool installation remain outside both contexts.
  Their ownership can be resolved as capabilities migrate, preserving shared
  chart-artifact and tool contracts. In chart commands, "chart" means a directory
  under a Helm directory.
- Keep external terms as they are: Distribution, and the application names EWB, EAS,
  HCS and web client.

Shared support is not another bounded context:

| Location under `src/zep_dev/` | Owns |
| --- | --- |
| `charts/metadata.py`, `charts/version.py`, `charts/runtime_contract.py` | Shared chart schemas, version rules and runtime-contract support |
| `charts/utils.py` | Chart discovery, chart-testing configuration and chart-path handling |
| `infrastructure/execution.py`, `infrastructure/tools.py` | Command execution and managed-tool definitions, catalog, paths and resolution |
| `infrastructure/registry.py`, `infrastructure/github_api.py`, `infrastructure/container_engine.py` | Registry discovery and external integrations |

Execution validates managed tools. Tool support must not import execution or CLI
code; dependency tests enforce this direction. `cli.py` remains the application
entrypoint and `errors.py` the package-wide expected-failure contract.

## Rules for changes

- Test names state the rule they protect, in the ubiquitous language.
- When you add or change a term or rule, update the relevant context's language
  (terms and code anchors) or context document (rules and tests) in the same change.
- A rule with no validator or test is a convention. Prefer adding the test.
- Keep CLIs thin and behaviour callable without Click. Follow each context's
  layering rules; Development Environments configuration does no I/O and its
  integrations never import `lifecycle` or CLI code.
- Add CI capabilities as capability-named modules and tests. Do not introduce
  layers or generic task abstractions for hypothetical future operations.
- Pass an explicit Environment target to every call that acts on an Environment's
  cluster or files (Kind, kubectl, Helm, Terraform). Never rely on the caller's
  Kubernetes context.

## Commands

From the repository root, with Python 3.12 or later:

```sh
make check-zep-dev test-zep-dev
git diff --check
```

Human documentation: [README](zep-dev/README.md).
