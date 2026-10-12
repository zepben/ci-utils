"""Environment-scoped Terraform roots and isolated subprocess execution."""

import json
import os
import shutil
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict

from zep_dev.development_environments.cnpg import DatabaseConnection
from zep_dev.development_environments.distributions import ChartName
from zep_dev.development_environments.services import CnpgService
from zep_dev.development_environments.target import (
    ExecutionTarget,
    kubernetes_namespace,
    private_target_directory,
    private_write,
)
from zep_dev.development_environments.templates import EnvironmentTemplate
from zep_dev.shared import execute


class RuntimeModule(TypedDict):
    source: str
    namespace: str
    database: str


@dataclass(frozen=True)
class RuntimeDatabase:
    application: ChartName
    service_name: str
    service: CnpgService
    module: Path


def runtime_state(target: ExecutionTarget) -> Path:
    return target.runtime_root / "terraform.tfstate"


def resolve_runtime_databases(
    template: EnvironmentTemplate, deployments_checkout: Path | None
) -> tuple[RuntimeDatabase, ...]:
    databases: list[RuntimeDatabase] = []
    for app, application in template.applications.items():
        if application.database is None:
            continue
        service_name = application.database.service
        service = template.services[service_name]
        if not isinstance(service, CnpgService):
            raise ValueError(f"database service {service_name} is not CNPG")
        if deployments_checkout is None:
            raise ValueError("deployments repository is required for runtime databases")
        module = (
            deployments_checkout
            / f"terraform/modules/kubernetes/{app}-kind-runtime-contract"
        ).resolve()
        if not module.is_dir():
            raise FileNotFoundError(f"runtime wrapper for {app} not found: {module}")
        databases.append(RuntimeDatabase(app, service_name, service, module))
    return tuple(databases)


def generate_runtime_root(
    target: ExecutionTarget,
    databases: Sequence[RuntimeDatabase],
) -> Path:
    """Regenerate configuration, never deleting an existing runtime state file."""
    root = target.runtime_root
    modules: dict[str, RuntimeModule] = {}
    inputs: dict[ChartName, DatabaseConnection] = {}
    for database in databases:
        app = database.application
        service = database.service
        source = os.path.relpath(database.module, start=root)
        modules[f"{app}_runtime_contract"] = {
            "source": source if source.startswith(".") else f"./{source}",
            "namespace": "${var.namespace}",
            "database": f"${{var.databases.{app}}}",
        }
        namespace = service.namespace or target.namespace
        inputs[app] = {
            "host": f"{database.service_name}-rw.{namespace}.svc.cluster.local",
            "port": 5432,
            "name": service.database,
            "username": service.owner,
            "password": service.password,
        }
    config = {
        "terraform": {
            "required_version": ">= 1.10.0",
            "required_providers": {
                "kubernetes": {"source": "hashicorp/kubernetes", "version": "~> 2.0"}
            },
        },
        "provider": {
            "kubernetes": {
                "config_path": "${var.kubeconfig}",
                "config_context": "${var.context}",
            }
        },
        "variable": {
            "namespace": {"type": "string"},
            "kubeconfig": {"type": "string"},
            "context": {"type": "string"},
            "databases": {
                "type": "map(object({host=string, port=number, name=string, username=string, password=string}))",
                "sensitive": True,
            },
        },
        "module": modules,
    }
    variables = {
        "namespace": target.namespace,
        "kubeconfig": str(target.kubeconfig),
        "context": target.context,
        "databases": inputs,
    }
    private_target_directory(target, root)
    private_write(root / "main.tf.json", json.dumps(config, indent=2) + "\n")
    private_write(
        root / "terraform.tfvars.json", json.dumps(variables, indent=2) + "\n"
    )
    return root


@contextmanager
def terraform_environment(target: ExecutionTarget) -> Generator[dict[str, str]]:
    with TemporaryDirectory(prefix="zep-dev-terraform-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        home = temporary_root / "home"
        data = temporary_root / "data"
        cli_config = temporary_root / "terraform.tfrc"
        home.mkdir()
        data.mkdir()
        cli_config.touch()
        yield {
            "PATH": os.environ.get("PATH", os.defpath),
            "KUBECONFIG": str(target.kubeconfig),
            "KUBE_CONFIG_PATH": str(target.kubeconfig),
            "HOME": str(home),
            "TF_DATA_DIR": str(data),
            "TF_CLI_CONFIG_FILE": str(cli_config),
        }


def terraform_init(root: Path, env: Mapping[str, str]) -> None:
    args = ["terraform", f"-chdir={root}", "init", "-backend=false", "-input=false"]
    if (root / ".terraform.lock.hcl").is_file():
        args.append("-lockfile=readonly")
    execute(*args, env=env)


def _apply_with_state(
    target: ExecutionTarget, root: Path, namespace: str, state: Path
) -> Path:
    if state.is_symlink():
        raise ValueError(f"Terraform state is a symlink: {state}")
    private_target_directory(target, state.parent)
    with terraform_environment(target) as env:
        terraform_init(root, env)
        execute(
            "terraform",
            f"-chdir={root}",
            "apply",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
            env=env,
        )
    return state


def apply_terraform(target: ExecutionTarget, root: Path, namespace: str) -> Path:
    """Apply a standalone root using its Environment-scoped state key."""
    valid_namespace = kubernetes_namespace(namespace)
    absolute_root = root.resolve()
    if not absolute_root.is_dir():
        raise FileNotFoundError(f"Terraform root does not exist: {absolute_root}")
    state = target.standalone_state(absolute_root, valid_namespace)
    return _apply_with_state(target, absolute_root, valid_namespace, state)


def destroy_terraform(target: ExecutionTarget, root: Path, namespace: str) -> None:
    valid_namespace = kubernetes_namespace(namespace)
    absolute_root = root.resolve()
    if not absolute_root.is_dir():
        raise FileNotFoundError(f"Terraform root does not exist: {absolute_root}")
    state = target.standalone_state(absolute_root, valid_namespace)
    if state.is_symlink():
        raise ValueError(f"Terraform state is a symlink: {state}")
    if not state.is_file():
        raise FileNotFoundError(f"Terraform state does not exist: {state}")
    with terraform_environment(target) as env:
        terraform_init(absolute_root, env)
        execute(
            "terraform",
            f"-chdir={absolute_root}",
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={valid_namespace}",
            env=env,
        )
    shutil.rmtree(state.parent)


def apply_runtime(
    target: ExecutionTarget,
    databases: Sequence[RuntimeDatabase],
) -> Path | None:
    if not databases and not runtime_state(target).is_file():
        return None
    root = generate_runtime_root(target, databases)
    return _apply_with_state(target, root, target.namespace, runtime_state(target))
