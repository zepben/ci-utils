import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

import local_k8s.cli as cli_module
from local_k8s.cli import add_bin_dir_to_path, cli


@patch.object(cli_module, "add_bin_dir_to_path")
def test_cli_calls_add_bin_dir_to_path(mock_add_bin_dir_to_path: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["tools", "--help"])

    assert result.exit_code == 0
    mock_add_bin_dir_to_path.assert_called_once()


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
