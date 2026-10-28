# Context: Development Environments

The only bounded context in `zep-dev` today. Terms are defined in
[language.md](language.md). Code: `src/zep_dev/development_environments/`.
Tests: `tests/development_environments/`.

## Purpose

Describe a coherent Zepben system once, supply machine-specific details separately,
and create, reuse, inspect and destroy named local Kubernetes Environments from it,
so integration defects are found before staging.

| Document | Question it answers | Shared between developers and CI? |
| --- | --- | --- |
| Distribution | What charts make up the system? | Yes |
| Template | How are they deployed and configured? | Yes |
| Bindings | Where do inputs live on this machine? | No |

Not in scope: application integration tests (application teams own them),
production deployment, CI job selection, and checking that selected charts work
together.

## Context map

| Neighbour | Direction | Relationship |
| --- | --- | --- |
| Kind, kubectl, Helm, Terraform, Podman/Docker, GHCR/OCI, GitHub API and Actions, and the Kind wrappers in Application repositories | Upstream | We conform to their commands and formats. `kind.py`, `kubernetes.py`, `helm.py`, `terraform.py` and `github_api.py` translate our model into their terms and keep tool details out of the core. |
| Application teams' integration tests, CI | Downstream | They consume `environment describe` JSON and the kubeconfig path (see Contracts and limits). |
| Chart CI (`zep-dev chart ...`), tool installation | Separate | A future CI context will own them. They must not import this package (enforced). In that code "chart" means a directory under a Helm directory. |

## Rules

Behavior that must survive a change. Rules about field validity are not repeated
here: read `EnvironmentTemplate.valid_references` and `templates.validate_distribution`
for Template and Distribution cross-references, `distributions.ChartLocator` (a
Locator has exactly one field), `documents.UniqueKeyLoader` (duplicate YAML keys are
rejected) and `local_inputs.py` for Bindings.

**Identity and targeting** (tests: `test_target.py`, `test_kind_targeting.py`,
`test_terraform_targeting.py`)

- An Environment is identified by its name alone. A name is validated before any path
  is derived from it.
- Every call that acts on an Environment's cluster or files (Kind, kubectl, Helm,
  Terraform) targets it explicitly. Inherited Kubernetes and Helm context cannot
  redirect it (`target.kubernetes_environment`).
- A supporting service uses the Environment namespace unless it names another
  (`ExecutionTarget.namespace_for`).
- Different names never share a cluster, namespace or files.

**Creation, reuse and failure** (tests: `test_lifecycle_policy.py`,
`test_lifecycle_composition.py`, `test_provisioning_composition.py`,
`test_git_cache.py`)

- Preflight resolves and validates everything before the cluster or operational
  directory changes.
- Creation refuses an existing cluster unless reuse is requested. A stale operational
  directory is removed first, and a cleanup failure stops creation.
- Creation never starts a chart build. A missing source chart is refused before any
  change.
- Supporting services run in Template order, with no dependency graph. Runtime
  resources are applied before application manifests and charts.
- Every selected chart whose revision has a Kind wrapper gets it applied, with the
  Application's `databases` connections, which may be none. For `local: true` the
  revision is the chart's checkout. For other Locators it is the commit recorded in
  the published chart's `zepben.com/source-commit` annotation, which Terraform
  fetches with a `git::` source. A wrapper applies a runtime contract, so a published
  chart without `zepben.com/runtime-contract-ref`, or without its source commit, is
  treated as having no wrapper and its repository is not fetched. Preflight refuses
  `databases` declared for an Application whose wrapper cannot be located, and a
  commit that is not on a branch or tag.
- On reuse, a supporting Helm release that is absent or `uninstalled` is installed, one
  that is `deployed` is not reinstalled, and any other status is an error.
- A failure after creation begins keeps the partial Environment.

**Destroy** (tests: `test_lifecycle_policy.py`)

- Destroy needs only the name. It removes the operational directory and keeps bound
  inputs, the Template and the Distribution. If cluster deletion fails, the directory
  stays.
- Regenerating Terraform configuration never deletes runtime state.

**Bindings and secrets**

- Bindings never hold application secret values. A secret source names exactly one of
  `env` or `file`, and is read when the Secret is created.
- Only inputs a Template requires are resolved.

**Layering** (tests: `tests/test_architecture.py`)

- Code outside the CLI modules does not import Click or CLI modules.
- Configuration modules (`templates`, `bindings`, `names`, `services`,
  `distributions`) read no files, run no commands and make no network requests.
- Integrations do not import `lifecycle` or CLI code.
- Nothing outside this package imports it, except `zep_dev/cli.py`, which registers its
  commands.

Workflows call configuration and integrations. Integrations may use configuration
and each other. The CLI parses arguments and calls workflows or integrations.

**Typing** (tests: `tests/test_architecture.py`)

- A wildcard `match` case only calls `assert_never`, so mypy reports a kind left
  unhandled.
- Behavior that depends on the kind of supporting service or chart reference is
  chosen with a `match` that names every kind. `isinstance` on either only filters.

## Contracts and limits

User-visible promises that a change must not break:

- `environment kubeconfig <name>` prints only the absolute kubeconfig path to stdout,
  regenerating a missing file at the conventional location. Diagnostics go to stderr.
- `environment describe <name>` prints one JSON document: `name`,
  `kubernetes: {kubeconfig, context}`, and `applications` keyed by root chart name,
  each with `namespace` and `endpoints` (`http` is the supported endpoint). It does
  not check readiness. It lists application releases that carry the Helm label
  `zepben.com/environment=<name>`; unmarked and supporting releases are excluded.
  HTTP discovery supports a TCP NodePort named `http` with
  `externalTrafficPolicy: Cluster`, bound on IPv4 loopback. Unsupported exposure is
  omitted with a diagnostic, and distinct URLs for one connection are an error. A
  failure prints no partial JSON (tests: `test_discovery.py`).
- `environment list` prints the sorted names of live zep-dev Kind clusters. It does
  not inspect operational directories, and a listed cluster may be partial.
- Creation succeeding means required provisioning and readiness checks completed. It
  does not mean application tests ran or passed.

Limits and their reasons:

- There is no saved lifecycle status. "Partial" and "ready" are observations. A saved
  operational directory cannot recover the original Template, resolved charts or
  input values.
- No lock protects concurrent changes to one Environment. Different names are
  isolated, but host ports and shared writable inputs can still conflict.
- Reuse is not reconciliation. Editing a Template alone changes nothing. Missing
  Terraform runtime state does not prove its resources are gone: a fresh apply is
  attempted, and lost state cannot be reconstructed.
- A Distribution build only shows charts were available at that time. A pull request
  or branch can advance before creation, which resolves again and may select a chart
  that is not yet available. A missing version-selected chart is an error, because a
  version cannot trigger a build.
- For `local: true`, build and create from the chart's checkout. Uncommitted changes
  share a version, so rebuild after editing.
- Argo repository integration needs a Kind worker node, because repo-server is
  scheduled away from control-plane nodes. It mounts the checkout read-only and
  registers the repository. It creates no Argo Applications.
- A Kind wrapper's required `databases` keys are checked by Terraform at apply time,
  after the cluster and supporting services exist. Preflight does not read the
  wrapper's variables.
- Database connections are passed as a sensitive `databases` map to the
  application's Kind wrapper. Application resources use the Environment namespace
  even when the database service uses another. Runtime contracts cannot be applied
  directly; only their Kind wrappers can.
- `environment describe` assumes the caller shares the container host's loopback
  network. Remote-runtime address translation is unsupported.

## Creation flow

1. `cli.py` parses arguments and calls `lifecycle.create_environment()`.
2. Preflight loads and validates the documents, resolves inputs and generated
   resources, and checks that the selected charts are available. It changes nothing.
3. Preflight returns a creation plan: resolved inputs, execution target, chart
   references and provisioning data.
4. Creation checks whether the cluster exists and applies the create or
   explicit-reuse rules.
5. Provisioning uses the same plan for supporting services, secrets, runtime
   resources, application manifests and application charts.

Resolving once, in the plan, stops Locators and inputs from being resolved
differently during provisioning. A failure after a change begins keeps the partial
work for inspection or retry. Distribution build is independent of Environment
creation and lives in `chart_sources.py`.

## Module map

Roles. **Core**: the model and the rules that make an Environment safe and
predictable. **Supporting**: translates the model into tool commands, or serves it.
**Generic**: no Zepben domain knowledge; could be replaced by a library.

| Module | Role | Owns |
| --- | --- | --- |
| `names.py` | core | Environment, Kubernetes and Helm release name rules |
| `templates.py`, `services.py` | core | Template and supporting-service schemas, cross-reference rules |
| `distributions.py` | core | Distribution schema, Locators, chart order |
| `bindings.py` | core | Bindings schema |
| `chart_sources.py` | core | Locator resolution, OCI checks, Kind wrapper location, Distribution build (and a generic Git cache) |
| `lifecycle.py` | core | Preflight, creation plan, create, reuse, destroy, list, kubeconfig |
| `target.py` | core | Execution target, operational directory paths, child process environment |
| `local_inputs.py` | supporting | Bindings discovery, resolving host inputs |
| `local_charts.py` | supporting | Packaging working-tree charts for `local: true` |
| `kind.py`, `kubernetes.py`, `helm.py`, `terraform.py` | supporting | Tool commands and generated resources |
| `cnpg.py`, `argo.py`, `supporting.py`, `manifests.py` | supporting | Supporting-service integrations and application manifests |
| `secrets.py`, `images.py` | supporting | Environment-targeted Secret and image operations |
| `discovery.py`, `diagnostics.py` | supporting | Describing a live Environment (`environment describe`), failure diagnostics |
| `cli.py` | supporting | Arguments, calling workflows, output |
| `documents.py`, `registry_config.py` | generic | Duplicate-safe YAML loading, registry authentication configuration |

Generated payload types live with their integration: Kubernetes resource types in
`kubernetes.py`, Argo values in `argo.py`, Terraform module inputs in
`terraform.py` (including the runtime contract's database connection), and EWB's
load-database configuration in `supporting.py`. A database service's provider
module supplies only its in-cluster address (`kubernetes.ServiceAddress`).

Outside the package: `shared.py`, `github_api.py`, `infrastructure/` (generic
helpers); `charts/`, `commands/chart/`, `commands/tools/`, `chart_version.py`,
`runtime_contract.py`, `models.py` (chart CI and tool installation, a future
context). `images pack` is
registered in this context's CLI but implemented in `charts/images.py`.

## Tests

Tests are grouped by what they isolate:

- **Configuration:** the model's rules, with no cluster.
- **Tool adapters:** commands and generated resources, with the command boundary
  replaced.
- **Lifecycle policy** (`test_lifecycle_policy.py`): sequencing and failure rules, with
  integration functions replaced.
- **Composition** (`test_*_composition.py`): configuration and integrations working
  together, with only command and network boundaries replaced.

A test's name states the rule it protects, so search the rule's words to find it.
Shared fixtures live in `conftest.py`, reusable test doubles in `tests/support/`.
Tests stub cluster and network boundaries. They do not establish compatibility with
live tools or with Kind wrappers. Test repositories come from `tests/support/git.py`,
which isolates Git from the developer's own configuration. The root `conftest.py`
pins the container engine, clears `CI_DUMP_DEBUG` and redirects `XDG_CACHE_HOME`
for every test.

## To change X, look at Y

| Change | Where |
| --- | --- |
| A Template, supporting-service, Distribution or Bindings field or rule | The concept's module: `templates.py`, `services.py`, `distributions.py`, `bindings.py` |
| A new kind of supporting service | A schema in `services.py` (add it to `SupportingService`), its integration module, and its dispatch in `lifecycle.provision_services` |
| A new kind of database service | A schema in `services.py` with `database`, `databases`, `owner` and `password`, added to `DatabaseService`; an integration module that provisions it and returns its `address`; cases in `EnvironmentTemplate.database_service`, `terraform.database_address` and `lifecycle.provision_services`. mypy reports each missing case |
| Creation order, reuse policy or failure handling | `lifecycle.py` |
| How a Locator resolves or a Distribution builds | `distributions.py` (schema), `chart_sources.py` (behavior) |
| A tool command or generated payload | The tool's module (`kind`, `kubernetes`, `helm`, `terraform`). Keep the explicit target argument |
| How an Environment is addressed or what a child process inherits | `target.py` |
| CLI arguments or output | `cli.py`. Behavior stays in the modules it calls |
