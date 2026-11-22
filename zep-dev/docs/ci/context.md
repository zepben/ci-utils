# Context: CI

Code: `src/zep_dev/ci/`. Tests: `tests/ci/`.
Terms: [language.md](language.md).

## Purpose and scope

Provide reusable repository checks and maintenance operations that behave
consistently when invoked locally or by CI. CI names the responsibility, not a
requirement to run on a CI runner.

The direction is to move reusable behaviour out of Bash, workflow YAML and pipeline
images into independently testable Python. Version manipulation, release checks
and project-file updates are possible additions, not implemented capabilities.
See [RFC 0007: CI stack improvements](https://github.com/zepben/deployments/blob/main/docs/rfcs/0007-ci-stack-improvements/README.md).

## Context map

| Neighbour | Responsibility and relationship |
| --- | --- |
| GitHub workflows | Call operations; decide when and where work runs, and supply permissions, credentials and job dependencies. |
| Repository Makefiles | Provide consistent project entrypoints and compose project-specific tasks, calling the same operations locally and in CI. |
| Project tools (Maven, npm, dotnet and others) | Own ecosystem-specific work. CI operations may call them rather than reimplement them. |
| Git, GitHub and other external services | Supply history, metadata and external effects through their commands and APIs. |
| Pipeline images | Supply execution environments and caches, rather than own repository-maintenance policy. |
| [Development Environments](../development_environments/context.md) | Separate context. Neither context imports the other; both may use shared infrastructure. |

Existing chart commands and tool installation remain outside this package. Their
ownership can be resolved as capabilities migrate; shared chart-artifact contracts
and tool execution must remain available to their existing consumers.

## Rules and structure

Dependency rules are enforced by `tests/test_architecture.py`:

- The CLI parses arguments, calls operations and reports results. Non-CLI modules
  do not import Click or CLI modules.
- The package is private. The root `zep_dev.cli` may import `ci.cli` to register
  commands; other code, including shared infrastructure, must not import it.
- CI does not import Development Environments.

Keep each capability's behaviour callable without Click. Pure rules should be
functions testable without Git, network access or installed project tools.
Document each operation's prerequisites and effects; running locally does not
implicitly make an operation read-only.

| Location | Owns |
| --- | --- |
| `ci/cli.py` | Command registration, arguments and output |
| `ci/news.py` | NEWS generation and its repository operations |
| `infrastructure/` (outside the context) | Shared GitHub client, command execution, managed-tool support and registry discovery |

Add capability-named modules as behaviour is added. Keep related rules and
orchestration together. Extract helpers or adapters when there is a clear
responsibility or actual reuse, not to populate predetermined layers.

## Tests

Group tests by capability under `tests/ci/`. Test pure rules directly, replace
command and network boundaries for integration behaviour, and invoke the CLI when
arguments, output or error handling are the subject. Apply CLI fixtures only where
needed. Split test files when that makes them easier to navigate.

When adding a capability, add its code and tests, document its command contract,
and extend this module map and the glossary only with concepts it introduces.
