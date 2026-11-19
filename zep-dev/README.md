# Zep Dev

`zep-dev` creates local Kubernetes development Environments and provides chart utilities and repository operations for local and CI use.

- A **Template** ([example](examples/integration/template.yaml)) defines how the Environment is deployed and configured.
- A **Distribution** ([example](examples/integration/distribution.yaml)) selects the application charts.
- **Bindings** ([example](examples/bindings.yaml)) supply the machine-local paths and secret sources the Template needs.

## Clanker Experiment

The tool uses a small subset of [Domain-Driven Design](https://en.wikipedia.org/wiki/Domain-driven_design) as an experiment in LLM-assisted development. Each bounded context defines its own language, rules and code ownership. The aim is to make changes easier to place and architectural mistakes easier to detect; whether this improves LLM-assisted development remains an experiment.

| Context | Responsibility | Documentation |
| --- | --- | --- |
| Development Environments | Create, reuse, inspect and destroy named local Kubernetes Environments. | [Context](docs/development_environments/context.md), [language](docs/development_environments/language.md) |
| CI | Reusable repository checks and maintenance operations, callable locally or by CI. | [Context](docs/ci/context.md), [language](docs/ci/language.md) |

Use the relevant context's terms in code, tests, errors and documentation. Tests enforce the dependency boundaries. Existing chart and tool utilities remain outside these contexts, with shared contracts available to their consumers.

## Examples

[examples/](examples/) holds a Template, a Distribution and Bindings.

Before running the tool, you need to setup the [Bindings](examples/bindings.yaml) on your machine:

```bash
mkdir -p ~/.config/zep-dev
cp zep-dev/examples/bindings.yaml ~/.config/zep-dev/bindings.yaml
```
Then update the paths within.

Once that is done, you can execute the commands and create/interact/destroy your env:

```sh
zep-dev environment create --template zep-dev/examples/integration/template.yaml
zep-dev environment list
zep-dev environment describe integration
zep-dev environment destroy integration
```

The example template publishes an address for the map. It is listed under `addresses` by:

```bash
zep-dev environment describe integration
```

It should be accessible in the browser on http://127.0.0.1:8080.

## Development

From the repository root, using Python 3.12 or later:

```sh
make check-zep-dev test-zep-dev
```
