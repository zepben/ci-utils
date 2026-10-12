# Zep Dev

`zep-dev` creates named, local Kubernetes development Environments on Kind.
A Template defines the environment. A Distribution selects application charts.
Bindings supply machine-local paths and secret sources for the Template’s inputs.

## Find the right documentation

- [Create and use an Environment](#create-and-use-an-environment) and the
  [examples](#templates-and-examples) show how to run the tool.
- The [configuration and behavior reference](docs/reference.md) defines terms,
  configuration rules, ownership, and command behavior.
- The [package architecture](docs/architecture.md) maps modules, dependencies,
  tests, and common extension points for maintainers.

## Create and use an Environment

Save this minimal Template as `minimal.yaml`. It creates cluster
`zep-dev-minimal` and namespace `minimal`, with no Distribution, supporting
services, or local inputs:

```yaml
metadata:
  name: minimal
cluster:
  kind:
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
      - role: control-plane
```

```sh
zep-dev environment create --template minimal.yaml
zep-dev environment list
zep-dev environment kubeconfig minimal
KUBECONFIG="$(zep-dev environment kubeconfig minimal)" kubectl get nodes
zep-dev environment destroy minimal
```

Set `KUBECONFIG` for external clients. Creation refuses an existing cluster
unless `--allow-reuse` is supplied. See the
[behavior reference](docs/reference.md) for reuse, failure,
and destruction rules. Environment creation does not run application integration
tests.

`environment list` prints the names of live zep-dev Kind clusters, one per line.
It does not report state directories whose clusters are absent or indicate whether
creation completed successfully.

## Templates and examples

The integration example creates EWB, EAS, and the web client, plus CNPG and
an EAS database. Read its documents in this order:

1. [Distribution](examples/integration/distribution.yaml) selects published
   versions of the three application charts.
2. [Template](examples/integration/template.yaml) references that Distribution
   and defines the cluster, supporting services, application values, and required
   local inputs. Its manifest path is relative to the Template.
3. [Bindings](examples/bindings.yaml) supplies this machine’s `ewb-data`
   directory and `deployments` checkout. The same Template can use different
   paths on another machine.

The example requires registry access, an EWB data directory, and a `deployments`
checkout containing `eas-kind-runtime-contract`. It reserves host ports 8080
and 8081. After configuring Bindings as described below, run from the repository
root:

```sh
zep-dev environment create --template zep-dev/examples/integration/template.yaml
zep-dev environment destroy integration
```

The integration Distribution contains illustrative version selections. Confirm the OCI artifacts
are available for the configured version before creation; version selection does
not build them. `zep-dev distribution build --distribution <path>` resolves source
selections and can dispatch their builds. Creation resolves and installs only
published artifacts. The EAS/HCS database path requires the matching Kind runtime
wrapper in the bound deployments checkout. The base runtime-contract modules are
not interchangeable with those wrappers.

See the [configuration and behavior reference](docs/reference.md) for Template
relationships, validation rules, and installation behavior.

## Machine-local inputs

Copy [the Bindings example](examples/bindings.yaml) to `.zep-dev/bindings.yaml`,
or set `ZEP_DEV_BINDINGS` to its path. Set it to a scratch file containing `{}`
when you need to bypass an outdated machine default. Replace `/home/alice/...`
with existing absolute local paths. See
[Resolve local inputs](docs/reference.md#resolve-local-inputs)
for discovery and validation, [secret sources](docs/reference.md#secret-sources)
for secret Bindings, and [Argo repository setup](docs/reference.md#argo-repository-setup)
for consuming a local checkout through Argo.

## Other commands

```sh
zep-dev images list --environment minimal
zep-dev images dump --environment minimal --output images.tar
zep-dev images load --environment minimal --archive images.tar
zep-dev images pack --helm-dir path/to/helm --output images.tar
zep-dev secrets create --environment minimal --namespace test --ci-secrets-file secrets.yaml
zep-dev terraform apply --environment minimal --root path/to/module --namespace test
zep-dev terraform destroy --environment minimal --root path/to/module --namespace test
zep-dev chart lint --helm-dir path/to/helm --chart charts/example
zep-dev tools install
```

Running-cluster image, Secret, and Terraform commands require `--environment`.
`images pack`, static chart commands, Distribution build, and tool installation
do not. Use `zep-dev --help` and the command's `--help` for exact options. The
standalone `--ci-secrets-file` format is separate from Template secret Bindings.

Application teams own integration tests.

## Development

From the repository root, using Python 3.14:

```sh
make check-zep-dev test-zep-dev
git diff --check
```

The root `make check` also runs staged formatting and can modify files.
