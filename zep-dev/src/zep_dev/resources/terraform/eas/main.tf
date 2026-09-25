# Kind-local wiring for eas-runtime-contract.
# Fixed Kind-only database_url credentials must match examples/profiles/platform.yaml.
module "eas_runtime_contract" {
  source = "__MODULE_SOURCE__"

  namespace    = var.namespace
  database_url = "jdbc:postgresql://eas-kind-pg-rw.${var.namespace}.svc.cluster.local:5432/eas?user=eas&password=eas"
}
