"""Environment-scoped Terraform roots and isolated subprocess execution."""

import json
import os
import shutil
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict, assert_never

from zep_dev.development_environments import cnpg
from zep_dev.development_environments.distributions import ChartName
from zep_dev.development_environments.kubernetes import ServiceAddress
from zep_dev.development_environments.services import CnpgService, DatabaseService
from zep_dev.development_environments.target import (
    ExecutionTarget,
    cache_home,
    kubernetes_name,
)
from zep_dev.development_environments.templates import (
    DatabaseReference,
    EnvironmentTemplate,
)
from zep_dev.errors import ZepDevError
from zep_dev.shared import execute


class DatabaseConnection(TypedDict):
    """One entry of a runtime contract's `databases` variable."""

    host: str
    port: int
    name: str
    username: str
    password: str


class RuntimeModule(TypedDict):
    source: str
    namespace: str
    databases: str


@dataclass(frozen=True)
class RuntimeApplication:
    application: ChartName
    databases: dict[str, DatabaseConnection]
    module: Path | str


def runtime_state(target: ExecutionTarget) -> Path:
    return target.runtime_root / "terraform.tfstate"


def database_address(
    target: ExecutionTarget, name: str, service: DatabaseService
) -> ServiceAddress:
    match service:
        case CnpgService():
            return cnpg.address(target, name, service)
        case _:
            assert_never(service)


def database_connection(
    target: ExecutionTarget, template: EnvironmentTemplate, reference: DatabaseReference
) -> DatabaseConnection:
    service = template.database_service(reference.service)
    if service is None:
        raise ValueError(f"{reference.service} is not a database service")
    address = database_address(target, reference.service, service)
    return {
        "host": address.host,
        "port": address.port,
        "name": reference.database,
        "username": service.owner,
        "password": service.password,
    }


def resolve_runtime_applications(
    target: ExecutionTarget,
    template: EnvironmentTemplate,
    kind_wrappers: Mapping[ChartName, Path | str],
) -> tuple[RuntimeApplication, ...]:
    """One runtime application per located Kind wrapper; `databases` may be empty."""
    applications: list[RuntimeApplication] = []
    for app, module in kind_wrappers.items():
        application = template.applications.get(app)
        references = application.databases if application is not None else {}
        databases = {
            name: database_connection(target, template, reference)
            for name, reference in references.items()
        }
        applications.append(RuntimeApplication(app, databases, module))
    return tuple(applications)


def generate_runtime_root(
    target: ExecutionTarget,
    applications: Sequence[RuntimeApplication],
) -> Path:
    """Regenerate configuration, never deleting an existing runtime state file."""
    root = target.runtime_root
    modules: dict[str, RuntimeModule] = {}
    inputs: dict[ChartName, dict[str, DatabaseConnection]] = {}
    for application in applications:
        app = application.application
        match application.module:
            case Path():
                source = os.path.relpath(application.module, start=root)
                if not source.startswith("."):
                    source = f"./{source}"
            case str():
                source = application.module
        modules[f"{app}_runtime_contract"] = {
            "source": source,
            "namespace": "${var.namespace}",
            "databases": f"${{var.databases.{app}}}",
        }
        inputs[app] = application.databases
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
                "type": "map(map(object({host=string, port=number, name=string, username=string, password=string})))",
                "sensitive": True,
            },
        },
    }
    if modules:
        config["module"] = modules
    variables = {
        "namespace": target.namespace,
        "kubeconfig": str(target.kubeconfig),
        "context": target.context,
        "databases": inputs,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.tf.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    (root / "terraform.tfvars.json").write_text(
        json.dumps(variables, indent=2) + "\n", encoding="utf-8"
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
        # TF_DATA_DIR is fresh per apply, so providers come from the plugin cache.
        plugins = cache_home() / "zep-dev" / "terraform-plugins"
        plugins.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "KUBECONFIG": str(target.kubeconfig),
            "KUBE_CONFIG_PATH": str(target.kubeconfig),
            "HOME": str(home),
            "TF_DATA_DIR": str(data),
            "TF_CLI_CONFIG_FILE": str(cli_config),
            "TF_PLUGIN_CACHE_DIR": str(plugins),
        }
        # Kind wrappers are fetched from GitHub over SSH, which needs the user's agent.
        if agent := os.environ.get("SSH_AUTH_SOCK"):
            env["SSH_AUTH_SOCK"] = agent
        yield env


def terraform_init(root: Path, env: Mapping[str, str]) -> None:
    args = ["terraform", f"-chdir={root}", "init", "-backend=false", "-input=false"]
    if (root / ".terraform.lock.hcl").is_file():
        args.append("-lockfile=readonly")
    execute(*args, env=env)


def _apply_with_state(
    target: ExecutionTarget, root: Path, namespace: str, state: Path
) -> Path:
    if state.is_symlink():
        raise ZepDevError(f"Terraform state is a symlink: {state}")
    state.parent.mkdir(parents=True, exist_ok=True)
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
    valid_namespace = kubernetes_name(namespace)
    absolute_root = root.resolve()
    if not absolute_root.is_dir():
        raise ZepDevError(f"Terraform root does not exist: {absolute_root}")
    state = target.standalone_state(absolute_root, valid_namespace)
    return _apply_with_state(target, absolute_root, valid_namespace, state)


def destroy_terraform(target: ExecutionTarget, root: Path, namespace: str) -> None:
    valid_namespace = kubernetes_name(namespace)
    absolute_root = root.resolve()
    if not absolute_root.is_dir():
        raise ZepDevError(f"Terraform root does not exist: {absolute_root}")
    state = target.standalone_state(absolute_root, valid_namespace)
    if state.is_symlink():
        raise ZepDevError(f"Terraform state is a symlink: {state}")
    if not state.is_file():
        raise ZepDevError(f"Terraform state does not exist: {state}")
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
    applications: Sequence[RuntimeApplication],
) -> Path | None:
    if not applications and not runtime_state(target).is_file():
        return None
    root = generate_runtime_root(target, applications)
    return _apply_with_state(target, root, target.namespace, runtime_state(target))
