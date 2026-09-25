# Example Profiles

How to run the reference Kind platform. Concepts and invariants:
[docs/distribution-profile-bindings.md](../../docs/distribution-profile-bindings.md).

## What you get

`examples/profiles/platform.yaml` plus
`examples/distributions/platform.yaml` apply **ewb**, **eas**, **hcs**, and
**eas-web-client** into namespace `platform` from OCI chart pins.

- UI: `http://127.0.0.1:8080`
- API: `http://127.0.0.1:8081` (`authType: none`)

Runtime contracts use the same Terraform modules as production, with
Kind-local inputs. Chart identity stays on the Distribution; the Profile holds
Kind layout, CNPG, values, and mount **slots** only.

## Bindings (required locally)

Create a bindings file before apply. Do not commit personal paths with the
examples.

```yaml
deployments_root: /home/you/git/deployments
mounts:
  ewb-data: /home/you/worktmp/archive/max/ewb-data
```

First file found wins:

1. `ZEP_DEV_BINDINGS`
2. `./.zep-dev/bindings.yaml`
3. `${XDG_CONFIG_HOME:-~/.config}/zep-dev/bindings.yaml`

`deployments_root` must contain
`terraform/modules/kubernetes/{eas,hcs}-runtime-contract`.
`mounts.ewb-data` must be a directory of EWB network model data.

## Commands

From `zep-dev/` (with Kind/Podman env and `KUBECONFIG=/tmp/kind-k8s-conf.yaml`
set as in the [zep-dev README](../../README.md)):

```bash
zep-dev distribution build --distribution examples/distributions/platform.yaml
zep-dev platform apply --profile examples/profiles/platform.yaml
zep-dev platform destroy --profile examples/profiles/platform.yaml
```

Build checks that each Distribution pin exists in OCI (`version:` missing
fails; `pullRequest:` / `commit:` may dispatch CI then poll). Apply never
calls build. Destroy only needs Profile metadata (and any saved Terraform
state under `/tmp/zep-dev-terraform/`).

Refresh example pins using the comments in
`examples/distributions/platform.yaml`. GHCR auth is required for Helm and
image pulls.

## Not this path

Single-chart CI on `test-cluster` (`cluster create` / `chart test`) is
separate. See the zep-dev README and
[deployments testing and CI](https://github.com/zepben/deployments/blob/main/docs/deployment-pipeline/testing-and-ci.md).
