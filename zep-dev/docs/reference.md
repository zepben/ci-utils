# Configuration and behavior reference

`zep-dev` creates named local Kubernetes Environments for development and testing.
This reference defines configuration concepts, ownership, and command behavior.
The [README](../README.md) provides commands and runnable examples; the
[architecture guide](architecture.md) describes the implementation.

## Scope

`zep-dev` selects application charts and creates, reuses, and destroys local
Environments. Kind, Kubernetes, Helm, Terraform, and GitHub Actions provide
external services for those operations.
Application teams own integration tests; Environment creation does not run them.
Production deployment and CI job selection have separate owners.

## Terms

| Term | Meaning |
| --- | --- |
| **Environment** | A named local instance, including its Kind cluster and operational files. It may be only partly created. |
| **Environment Template (Template)** | A reusable document describing an Environment's cluster, supporting services, application configuration, and required local inputs. Its `metadata.name` names the Environment. |
| **Distribution** | A named selection of application charts. A selection uses a published version, a pull request, a branch, a commit, or the caller’s local chart working tree. It can be built without creating an Environment. |
| **Bindings** | Machine-local references that supply paths, checkouts, or secret sources for inputs declared by a Template. They do not contain application secret values. |
| **Application** | An EWB, EAS, HCS, or web client chart selected by a Distribution. |
| **Supporting service** | A facility an application or test needs, such as a database, operator, storage service, or Argo. A Template declares these under `services`. |

An application chart owns the resources packaged inside it, even if they serve
another application. The distinction between an application and a supporting
service follows its role in the Environment, not the team that built it.

## Relationships and rules

A Template may refer to a Distribution. Without one, it creates supporting
resources only and `applications` must be empty. With a Distribution, every
`applications` entry must name a selected chart. A selected chart need not have
an `applications` entry; another service can install it later.

An `applications.<name>.database.service` reference must name a CNPG supporting
service. Database configuration is supported for EAS and HCS and requires a
declared `deployments` repository input. Application resources use the Environment
namespace even when the CNPG service uses another namespace.

The Template declares local input names under `inputs`; Bindings supply their
sources on the current machine. A service that consumes a repository must name a
declared input. The declaration alone does not configure the service. The same
Template can therefore be used on different hosts with different Bindings.

The Environment name is its application namespace. Namespaced supporting services
use that namespace by default but may specify another. A service key names its
resource and cannot equal a selected application release name, even across
namespaces. Services run in Template order. Each configured readiness check must
finish before the next service starts; the Template has no dependency graph.

## Identity and ownership

`metadata.name` identifies an Environment on one host. A Template named
`integration` addresses Kind cluster `zep-dev-integration`, namespace
`integration`, and operational files under
`${XDG_STATE_HOME:-~/.local/state}/zep-dev/environments/integration/`.
Creation has no separate name override. Destruction needs only the name.

An Environment owns its cluster, the resources inside it, and its operational
files. It uses bound directories, checkouts, and secret sources without owning
them. Destruction removes owned resources and preserves those external inputs,
the Template, and the Distribution.

There is no separate Environment record or saved lifecycle status. The name
determines where the tool looks for the cluster and files. A saved operational
directory alone cannot recover the original Template, resolved charts, or input
values. Different Environment names identify separate clusters and files, but
host ports and shared writable inputs can still conflict.

## Build a Distribution

A Distribution selects each application chart by published version, pull request,
branch, commit, or `local: true`. Resolution produces a chart reference. It does
not check that the chart exists or that selected charts work together.

`zep-dev distribution build` packages local charts and checks remote selections
in OCI. For missing PR/branch/commit charts, it requests a build and waits for
publication. A missing version-selected chart is an error: a version cannot
trigger a source build. Required resolution, build, and publication failures are errors.

Success means the charts were available at that time. It does not certify
compatibility or prepare supporting services. A pull request or branch can advance
between build and Environment creation; creation resolves it again and may select
a chart that is not yet available.

For `local: true`, run build and creation from the chart's checkout. Build packages
working-tree chart changes locally; creation requires the saved package for the
computed version. Rebuild after edits: uncommitted changes share a version.

## Create an Environment

`zep-dev environment create --template <path>` uses the Template's
`metadata.name`. A Template without a Distribution creates supporting resources
only.

Before changing a cluster, the tool loads and validates the Template and any
Distribution. It rejects duplicate YAML keys, unknown schema fields, and invalid
references. Native Kind configuration, CNPG `spec`, and Helm `values` remain
free-form mappings. It resolves required local inputs and files, checks mounts
and manifest namespaces, and checks selected application-chart availability.
Creation uses the chart references resolved in this check; it does not request
application builds.

Creation refuses an existing cluster unless `--allow-reuse` is set. If the
cluster is absent but its operational directory remains, the tool warns on
stderr and removes that directory before creating the cluster. Cleanup failure
stops creation.

The tool creates the cluster and namespace, prepares storage classes, and
processes supporting services in Template order. It completes configured
readiness checks, then creates required Secrets, provisions application runtime
resources, applies additional application manifests, and installs selected
application charts. A namespaced application manifest must omit its namespace
or use the Environment namespace; its path is relative to the Template.

Success means required provisioning and configured readiness checks completed.
It does not mean application integration tests ran or passed.

## Resolve local inputs

A Template declares required inputs; Bindings supply their machine-local sources.
The tool reads the first existing Bindings file in this order: `ZEP_DEV_BINDINGS`,
`.zep-dev/bindings.yaml` in the working directory, then
`${XDG_CONFIG_HOME:-~/.config}/zep-dev/bindings.yaml`. An invalid selected file
is an error even if the Template uses no inputs. No file is needed when the
Template has no inputs and none is found.

Bound paths must be absolute. Mounts must name existing directories; referenced
Argo repositories must name Git checkout roots. A secret source in Bindings selects one
environment variable or file containing `KEY=value` entries. Missing required
sources are errors. The tool reads secret values when it uses them. Application
secret values belong in the source, not in Templates or Bindings. A CNPG service
may contain an explicit, disposable development password.

### Secret sources

A Template declares a secret input key and the Kubernetes Secret name:

```yaml
inputs:
  secrets:
    app-credentials:
      name: app-credentials
    other-credentials:
      name: other-credentials
```

Bindings maps those input keys to sources. Each source selects exactly one of
`env` or `file`:

```yaml
secrets:
  app-credentials:
    env: APP_CREDENTIALS
  other-credentials:
    file: /home/alice/secrets/other.env
```

`APP_CREDENTIALS` contains the `KEY=value` text itself, not a file path.
`file` names an absolute path to a file containing that text. For example,
`export APP_CREDENTIALS='USERNAME=developer'` supplies one entry. Values are
read when the Secret is created. These input declarations are independent of
application chart values; configure the chart to consume the named Secret.

## Argo repository setup

This Template installs Argo and prepares repository access. It supplies no
Argo Application; supply Applications separately to select repository paths
and sync resources. Check chart version availability and GHCR credentials
before creation.

```yaml
metadata:
  name: argo-example
cluster:
  kind:
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
      - role: control-plane
      - role: worker
services:
  argo-cd:
    type: helm
    chart: argo-cd
    repository: https://argoproj.github.io/argo-helm
    version: "10.3.2"
    namespace: argo-cd
    integration:
      type: argo-cd
      repositories:
        - deployments
      oci_repositories:
        - name: zepben-charts
          registry: ghcr.io
          repository: zepben/charts
    values:
      dex:
        enabled: false
      server:
        service:
          type: ClusterIP
inputs:
  repositories:
    - deployments
```

Use a `repositories.deployments` Binding pointing to an existing Git checkout
root, as in the [Bindings example](../examples/bindings.yaml). The integration
mounts that checkout read-only on the worker and configures Argo repo-server
with `file:///mnt/local-repos/<checkout-directory-name>`. The worker is required
because repo-server is scheduled away from control-plane nodes. The OCI entry
configures access to `ghcr.io/zepben/charts` using local registry credentials.
Repository registration does not create Applications or sync resources.

## Reuse an Environment

`--allow-reuse` permits another setup attempt against an existing cluster. It
does not fully reconcile the cluster with the Template. Editing a Template alone
does not change an Environment.

A supporting Helm release is identified by namespace and release name. Reuse
skips installation when that release is `deployed`. A release in any other
status is an error. Configured checks and related ConfigMap, load-database, and
Argo Secret actions still run. CNPG and raw services are reapplied. Existing
application Secrets retain their values; missing Secrets use the current bound
sources. Application charts use Helm upgrade or install.

Missing Terraform runtime state does not prove its resources are absent. The
tool attempts a fresh apply when required and reports failure; it cannot
reconstruct lost state. Required setup and readiness failures remain errors.
Reuse can leave old resources and partial new changes. Changed Bindings or
moving chart selections can also change the outcome of a later attempt. The
tool has no lock for concurrent changes to the same Environment.

## Handle failure

Preflight failure occurs before cluster mutation. Failure after creation begins
can leave a partial Environment. The tool reports the error and keeps the
Environment for inspection, explicit destruction, or another attempt with
`--allow-reuse`. It does not automatically destroy the whole Environment.
Individual external tools may roll back their own operations.

There is no saved lifecycle status. “Partial” and “ready” describe observed
outcomes. An application test can fail after Environment creation succeeds;
that does not change what creation established.

## Destroy an Environment

`zep-dev environment destroy <name>` needs only the name. It does not load a
Template, resolve a Distribution, or read Bindings. It deletes the named Kind
cluster before removing that Environment's operational directory. It preserves
external inputs and reusable documents.

An already absent cluster or directory counts as success. Lookup, deletion, and
cleanup failures are errors. If cluster deletion fails, operational files remain
for diagnosis and retry. Terraform runtime state under `terraform/runtime/` and
standalone state under `terraform/standalone/` are owned files removed after
cluster deletion succeeds.

## Obtain kubeconfig

`zep-dev environment kubeconfig <name>` requires the named cluster. It prints
only the absolute kubeconfig path to stdout, regenerating a missing file at the
conventional location. Diagnostics go to stderr. A stale file does not make an
absent cluster valid. Running-cluster image, Secret, and Terraform commands also
require an explicit Environment target; they do not use the caller's default
Kubernetes context.

## List Environments

`zep-dev environment list` prints sorted Environment names for live zep-dev Kind
clusters, one per line. It does not inspect operational directories. A directory
without a cluster is absent from the list, and a listed cluster may be partial:
the tool has no saved lifecycle status. An empty list prints nothing. Kind lookup
failures are errors.

See the [minimal quickstart](../README.md#create-and-use-an-environment) and
[integration example](../README.md#templates-and-examples) for complete
configuration documents and lifecycle commands.
