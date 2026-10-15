"""Dependency rules for configuration, workflows, and integrations."""

import ast
from importlib.util import resolve_name
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/zep_dev"
CONFIGURATION = {"templates", "bindings", "names", "services", "distributions"}
FEATURE = "zep_dev.development_environments"


def module_name(path: Path) -> str:
    parts = path.relative_to(SRC.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports(path: Path) -> set[str]:
    module = module_name(path)
    package = module if path.stem == "__init__" else module.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            base = resolve_name(prefix, package) if node.level else prefix
            base_path = SRC.parent.joinpath(*base.split("."))
            if base_path.is_dir():
                for alias in node.names:
                    candidate = base_path / alias.name
                    if (
                        candidate.with_suffix(".py").is_file()
                        or (candidate / "__init__.py").is_file()
                    ):
                        found.add(f"{base}.{alias.name}")
                    else:
                        found.add(base)
            else:
                found.add(base)
    return found


def cli_module(name: str) -> bool:
    return (
        name == "zep_dev.cli"
        or name == "zep_dev.development_environments.cli"
        or name in {"zep_dev.commands", "zep_dev.groups"}
        or name.startswith(("zep_dev.commands.", "zep_dev.groups."))
    )


def test_non_cli_modules_do_not_import_cli() -> None:
    violations = [
        f"{module_name(path)} -> {name}"
        for path in SRC.rglob("*.py")
        if not cli_module(module_name(path))
        for name in imports(path)
        if cli_module(name) or name == "click" or name.startswith("click.")
    ]
    assert violations == []


def test_configuration_does_not_import_effects_or_workflows() -> None:
    effects = {"click", "os", "requests", "socket", "subprocess", "sys"}
    violations = [
        f"{module_name(path)} -> {name}"
        for path in (SRC / "development_environments").glob("*.py")
        if path.stem in CONFIGURATION
        for name in imports(path)
        if name.split(".")[0] in effects
        or (
            name.startswith("zep_dev.")
            and not any(
                name == f"{FEATURE}.{module}" or name.startswith(f"{FEATURE}.{module}.")
                for module in CONFIGURATION
            )
        )
    ]
    assert violations == []


def test_integrations_do_not_import_lifecycle_or_cli() -> None:
    violations = [
        f"{module_name(path)} -> {name}"
        for path in (SRC / "development_environments").glob("*.py")
        if path.stem not in CONFIGURATION | {"__init__", "lifecycle", "cli"}
        for name in imports(path)
        if name == f"{FEATURE}.lifecycle"
        or name.startswith(f"{FEATURE}.lifecycle.")
        or cli_module(name)
    ]
    assert violations == []


def test_shared_capabilities_do_not_import_environment_code() -> None:
    support = [
        *[path for path in SRC.glob("*.py") if path.name != "cli.py"],
        *SRC.joinpath("charts").rglob("*.py"),
        *SRC.joinpath("infrastructure").rglob("*.py"),
    ]
    violations = [
        f"{module_name(path)} -> {name}"
        for path in support
        for name in imports(path)
        if name == FEATURE or name.startswith(f"{FEATURE}.")
    ]
    assert violations == []
