# Zep Dev

Reusable kubernetes cluster for development and CI. Requires kind installed https://kind.sigs.k8s.io/docs/user/quick-start/.

## Required Files

The tool requires two files:

* kind-cluster.yaml - configures kind. See [example](examples/kind-cluster.yaml).
* components.yaml - configures dependencies to be installed via helm when creating the kind cluster.

### ConfigMaps from files

A component can create ConfigMaps from files before its Helm release is installed:

```yaml
cluster_components:
  - name: database
    chart: example/database
    version: "1.0.0"
    namespace: test
    config_maps_from_file:
      - name: database-init
        from_file:
          init.sql: files/init.sql
```

Each ConfigMap uses its component namespace. On a reused Kind cluster, ConfigMaps are
applied again before Helm is skipped. See [`examples/components.yaml`](examples/components.yaml) for an example.

## Development

The Makefile in the root of the project contains some targets for interacting with the the tool. Simply run:

```shell
make check-zep-dev test-zep-dev
```

To execute the linters and tests. 

`zep-dev chart lint` and `zep-dev chart test` enforce the chart metadata schema
and YAML lint policy bundled with `zep-dev`.

To create a local kind cluster, you can run:
```shell
make setup-k8s
```

Be sure to set the env so kubectl and friends operate as expected:

```shell
export KUBECONFIG=/tmp/kind-k8s-conf.yaml
```
