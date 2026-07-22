# Local K8s

Reusable kubernetes cluster for development and CI. Requires kind installed https://kind.sigs.k8s.io/docs/user/quick-start/.

## Required Files

The tool requires two files:

* kind-cluster.yaml - configures kind. See [example](examples/kind-cluster.yaml).
* components.yaml - configures dependencies to be installed via helm when creating the kind cluster.

## Development

The Makefile in the root of the project contains some targets for interacting with the the tool. Simply run:

```shell
make check-local-k8s test-local-k8s
```

To execute the linters and tests. 

To create a local kind cluster, you can run:
```shell
make setup-k8s
```

Be sure to set the env so kubectl and friends operate as expected:

```shell
export KUBECONFIG=/tmp/kind-k8s-conf.yaml
```