# Zep Dev

CLI for local and CI Kubernetes work around Zepben charts.

Two different jobs share this tool. Do not mix them up.

| Job | What you use | Cluster name |
| --- | --- | --- |
| Single-chart CI / chart test | `kind-cluster.yaml` + `components.yaml` (or repo equivalents) | `test-cluster` |
| Full platform (multi-app Kind) | Distribution + Profile + Bindings | Profile `metadata.name` |

Mental model for the platform path:
[docs/distribution-profile-bindings.md](docs/distribution-profile-bindings.md).

Production chart and Argo flow:
[deployments deployment-pipeline](https://github.com/zepben/deployments/tree/main/docs/deployment-pipeline)
([testing and CI](https://github.com/zepben/deployments/blob/main/docs/deployment-pipeline/testing-and-ci.md)).

Requires [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/). This environment
uses rootless Podman; set `CONTAINER_HOST` and `KIND_EXPERIMENTAL_PROVIDER=podman`
before Kind commands. Kubeconfig for zep-dev Kind clusters is always
`/tmp/kind-k8s-conf.yaml`.

```bash
export PATH="$HOME/.local/share/ci-utils/bin:$HOME/.local/share/helm/bin:$PATH"
export CONTAINER_HOST=unix:///run/user/$(id -u)/podman/podman.sock
export KIND_EXPERIMENTAL_PROVIDER=podman
export KUBECONFIG=/tmp/kind-k8s-conf.yaml
```

## Platform (Distribution · Profile · Bindings)

Bring up ewb, eas, hcs, and eas-web-client from OCI pins into a Kind cluster.

1. Install tools / the CLI (`zep-dev tools install`, or your repo Makefile).
2. Write machine-local Bindings (see examples README). Do not commit personal paths.
3. Ensure charts exist, then apply:

```bash
zep-dev distribution build --distribution examples/distributions/platform.yaml
zep-dev platform apply --profile examples/profiles/platform.yaml
zep-dev platform destroy --profile examples/profiles/platform.yaml
```

Worked example and Bindings sample:
[examples/profiles/README.md](examples/profiles/README.md).

## Single-chart Kind (`test-cluster`)

Used by app-repo `make test` / CI chart install. Examples:

- [examples/kind-cluster.yaml](examples/kind-cluster.yaml)
- [examples/components.yaml](examples/components.yaml)

```bash
zep-dev cluster create --kind-config examples/kind-cluster.yaml \
  --components examples/components.yaml
# chart lint / test from an application helm/ tree
zep-dev chart lint --helm-dir …
zep-dev chart test --helm-dir …
zep-dev cluster teardown
```

`components.yaml` can declare Helm helpers, ConfigMaps from files, `wait_for`,
and EWB load-database credential wiring. See the examples file for the shape.

Platform Profiles must not use `metadata.name: test-cluster` (reserved).

## Development of zep-dev itself

From the ci-utils repo root:

```bash
make check-zep-dev test-zep-dev
```
