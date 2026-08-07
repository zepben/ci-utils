import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

import zep_dev.cli as cli_module
from zep_dev.cli import add_bin_dir_to_path, cli, configure_helm_registry


@patch.object(cli_module, "add_bin_dir_to_path")
@patch.object(cli_module, "configure_helm_registry")
def test_cli_configures_process_environment(
    mock_configure_helm_registry: MagicMock,
    mock_add_bin_dir_to_path: MagicMock,
) -> None:
    result = CliRunner().invoke(cli, ["tools", "--help"])

    assert result.exit_code == 0
    mock_add_bin_dir_to_path.assert_called_once()
    mock_configure_helm_registry.assert_called_once()


@patch.object(cli_module, "get_bin_dir")
def test_add_bin_dir_to_path_prepends(
    mock_get_bin_dir: MagicMock,
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mock_get_bin_dir.return_value = bin_dir

    with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=False):
        add_bin_dir_to_path()
        assert os.environ["PATH"] == f"{bin_dir.resolve()}{os.pathsep}/usr/bin:/bin"


@patch.object(cli_module, "resolve_registry_config")
def test_configure_helm_registry_sets_discovered_config(
    mock_resolve_registry_config: MagicMock,
    tmp_path: Path,
) -> None:
    registry_config = tmp_path / "config.json"
    mock_resolve_registry_config.return_value = registry_config

    with patch.dict(os.environ, {}, clear=True):
        configure_helm_registry()
        assert os.environ["HELM_REGISTRY_CONFIG"] == str(registry_config)


@patch.object(cli_module, "resolve_registry_config")
def test_configure_helm_registry_preserves_explicit_config(
    mock_resolve_registry_config: MagicMock,
) -> None:
    with patch.dict(
        os.environ,
        {"HELM_REGISTRY_CONFIG": "/explicit/config.json"},
        clear=True,
    ):
        configure_helm_registry()

    mock_resolve_registry_config.assert_not_called()
