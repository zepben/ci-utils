# Zep Dev

`zep-dev` creates local Kubernetes development Environments for local development and testing on CI.

- A **Template** ([example](examples/integration/template.yaml)) defines how the Environment is deployed and configured.
- A **Distribution** ([example](examples/integration/distribution.yaml)) selects the application charts.
- **Bindings** ([example](examples/bindings.yaml)) supply the machine-local paths and secret sources the Template needs.

## Clanker Experiment

The tool uses concepts from [Domain Driven Design](https://en.wikipedia.org/wiki/Domain-driven_design) as an experiment in LLM assisted development. The basic idea is to use a tightly defined language (Ubiquitous Language) consistently throughout the project. The definitions are in the [glossary](docs/language.md), and the goal is to use them consistently throughout the codebase, tests, docs etc. The theory is that this may assist with helping LLMs understand the codebase and not sloppify it, as things have a very specific place and meaning. TBD if this is effective.

In addition to the language, we have [domain context](docs/context.md) which is states the rules and contracts. This is the "Bounded Context" from DDD. It should help the LLM understand the rules of the game.

We additionally structure the code around this language and this context, and enforce it with unit tests. The idea is to provide quick feedback when the LLM violates a architectural rule.

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

The example template exposes an endpoint to access the map. This can be retrieved with:

```bash
zep-dev environment describe integration
```

It should be accessible in the browser on http://127.0.0.1:8080.

## Development

From the repository root, using Python 3.14:

```sh
make check-zep-dev test-zep-dev
```
