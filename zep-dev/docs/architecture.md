# Package architecture

`development_environments/` owns named local Environments and Distribution builds.
Configuration, lifecycle coordination, and external integrations are ordinary
modules in one feature package. Standalone chart utilities and tool installation
remain separate capabilities.

The [configuration and behavior reference](reference.md) defines Template,
Distribution, Bindings, Environment ownership, and command behavior. The
[README](../README.md) provides commands and examples.

## Package map

| Modules | Responsibility |
| --- | --- |
| `templates.py`, `services.py` | Template and supporting-service schemas; cross-reference rules. |
| `distributions.py`, `bindings.py`, `names.py` | Chart selections, machine-local source declarations, and name constraints. |
| `documents.py`, `local_inputs.py` | Duplicate-safe YAML loading, document-relative paths, and host input resolution. |
| `lifecycle.py` | Preflight, creation, reuse, destruction, listing, and kubeconfig lookup. |
| `target.py` | Explicit cluster targets, owned paths, private files, and child-process environment. |
| `chart_sources.py` | Chart resolution, Git cache, OCI checks, and Distribution builds. |
| `local_charts.py` | Caller checkout resolution, staged chart packaging, and versioned local artifacts. |
| `kind.py`, `kubernetes.py`, `helm.py`, `terraform.py` | Tool-specific commands and generated resources. |
| `cnpg.py`, `argo.py`, `supporting.py`, `manifests.py` | Supporting services and application resources. |
| `images.py`, `secrets.py` | Environment-targeted image and Secret operations. |
| `cli.py` | Arguments, capability invocation, and command output. |

Generated payload types live with their integration: Kubernetes resource types in
`kubernetes.py`, Argo values in `argo.py`, Terraform module inputs in `terraform.py`,
and the database connection format shared by provisioning code in `cnpg.py`.

## Dependency rules

Configuration models validate data without reading files, running commands, or
making network requests. For example, a Template checks that a mount names a
declared input; `local_inputs.py` checks that the bound host directory exists.
Configuration modules cannot import integrations, lifecycle workflows, or CLI code.

Lifecycle workflows call configuration and integration modules. Integrations can
use configuration and each other, but cannot import lifecycle workflows or CLI
code. For example, lifecycle code decides when a cluster may be reused; `kind.py`
checks its mounts and exports its kubeconfig.

Reusable code cannot import CLI modules or Click. Lifecycle commands call workflows;
image, Secret, and standalone Terraform commands resolve an Environment target and
call integrations directly.

`shared.py`, `github_api.py`, and `infrastructure/` provide reusable helpers without
importing development-environment code. Standalone chart utilities remain usable
without the Environment model.

## Creation flow

1. `cli.py` parses arguments and calls `lifecycle.create_environment()`.
2. Preflight loads and validates documents, resolves local inputs and generated
   resources, and checks selected chart availability without changing the cluster.
3. Preflight returns a `CreationPlan` containing the resolved inputs, target,
   chart references, and provisioning data.
4. Creation checks cluster existence and applies the create or explicit-reuse rules.
5. Provisioning uses the same plan for supporting services, Secrets, runtime
   resources, application manifests, and application charts.

Keeping resolution in the plan prevents chart selections and inputs from being
resolved differently during provisioning. Failures after mutation retain partial
work for inspection or retry. Distribution build is independent of Environment
creation and lives in `chart_sources.py`.

## Tests

`tests/development_environments/` is flat. Tests are named for configuration
concepts, external tools, CLI commands, lifecycle policy, lifecycle composition,
and provisioning composition. Focused lifecycle tests replace integration functions;
composed tests retain more real code and replace command or network boundaries.
Policy tests isolate sequencing and failures; composed tests check that
configuration and integrations work together.

Shared environment fixtures live in the feature's `conftest.py`; focused lifecycle
fixtures live with their tests. `tests/support/` contains reusable test doubles and
fixture contracts. [Dependency tests](../tests/test_architecture.py) enforce the
rules above.

Tests stub cluster and network boundaries. They do not establish live-tool or
cross-repository wrapper compatibility.

## Extending the tool

- Change configuration fields and rules in the corresponding concept module.
- Add a supporting-service schema in `services.py`, its integration implementation,
  and its dispatch in `lifecycle.py`.
- Change creation order, reuse policy, or failure handling in `lifecycle.py`.
- Change commands, generated payloads, or tool-specific checks in the relevant
  integration module; keep explicit targets.
- Change chart selection schemas in `distributions.py` and resolution or build
  behavior in `chart_sources.py`.
- Add CLI arguments and output in `cli.py`, with behavior owned by reusable modules.

Run `make check-zep-dev test-zep-dev` and `git diff --check` from the repository root.
