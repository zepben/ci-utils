# Kind-local wiring for hcs-runtime-contract.
# Fixed Kind-only DB locals must match examples/profiles/platform.yaml (user/password/host).
locals {
  hcm_namespace     = "hcs-${var.namespace}"
  cluster_role_name = "${var.namespace}-hcs-roles"
  pg_host           = "hcs-kind-pg-rw.${var.namespace}.svc.cluster.local"
  pg_user           = "hcs_kind"
  pg_password       = "hcs-kind-password"
  pg_port           = 5432
}

resource "kubernetes_namespace_v1" "hcm" {
  metadata {
    name = local.hcm_namespace
  }
}

module "hcs_runtime_contract" {
  source = "__MODULE_SOURCE__"

  namespace                       = var.namespace
  hcm_namespace                   = local.hcm_namespace
  service_name                    = "hcs"
  hcs_service_account_name        = "hcs-service-account"
  hcs_service_account_annotations = {}
  hcm_service_account_name        = "hcm-service-account"
  hcm_service_account_annotations = {}
  cluster_role_name               = local.cluster_role_name
  load_db = {
    host     = local.pg_host
    port     = local.pg_port
    name     = "load"
    username = local.pg_user
    password = local.pg_password
  }
  input_db = {
    host     = local.pg_host
    port     = local.pg_port
    name     = "input"
    username = local.pg_user
    password = local.pg_password
  }
  results_db = {
    host     = local.pg_host
    port     = local.pg_port
    name     = "results"
    username = local.pg_user
    password = local.pg_password
  }
  hcs_db = {
    host     = local.pg_host
    port     = local.pg_port
    name     = "hcs"
    username = local.pg_user
    password = local.pg_password
  }
  ewb = {
    host                = "ewb.${var.namespace}.svc.cluster.local"
    port                = 80
    authentication_mode = "NONE"
    client_id           = "kind-hcs-client"
    client_secret       = "kind-only-not-a-credential"
    issuer              = "https://issuer.invalid/kind"
    audience            = "kind-hcs"
    nmi_stored_in_mrid  = false
  }
  storage_backend_config = {
    type       = "s3"
    bucketName = "hcs-kind-fixture"
    region     = "ap-southeast-2"
  }
  parquet_config_maps = {
    result_processor = {
      RP__entrypoint_config_parquet_parquetOutputType = "S3"
      RP__entrypoint_config_parquet_s3Bucket          = "hcs-kind-fixture"
      RP__entrypoint_config_parquet_s3BasePath        = "results"
    }
    intrinsic = {
      IH__entrypoint_config_resultsConfig_parquet_parquetOutputType = "S3"
      IH__entrypoint_config_resultsConfig_parquet_s3Bucket          = "hcs-kind-fixture"
      IH__entrypoint_config_resultsConfig_parquet_s3BasePath        = "intrinsic"
    }
  }
  generator_java_tool_options        = "-XX:+UseContainerSupport -XX:MaxRAMPercentage=80"
  result_processor_java_tool_options = "-XX:+UseContainerSupport -XX:MaxRAMPercentage=80"
  intrinsic_java_tool_options        = "-XX:+UseContainerSupport -XX:MaxRAMPercentage=80"

  depends_on = [kubernetes_namespace_v1.hcm]
}
