import json
from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
from click import ClickException

from local_k8s.shared import execute
from local_k8s.static import CT_YAML


@click.command("list-changed")
@click.option(
    "--helm-dir",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
@click.option("--target-branch", default="main", show_default=True)
def list_changed(helm_dir: Path, target_branch: str) -> None:
    helm_dir = helm_dir.resolve()
    ct_path = helm_dir / CT_YAML
    if not ct_path.is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    # Get the root of our git repo.
    repo_root = Path(
        execute(
            "git",
            "-C",
            str(helm_dir),
            "rev-parse",
            "--show-toplevel",
            skip_resolve=True,
        ).strip()
    ).resolve()

    # ct list-changed operates a bit differently to the other CT commands.
    # It must be executed from the root of the repo, and the paths to
    # the chart-dir/config need to be relative not absolute. This is
    # why we convert to relative below, if that is not done, it asplodes.
    with chdir(repo_root):
        try:
            out = execute(
                "ct",
                "list-changed",
                "--config",
                str(ct_path.relative_to(repo_root)),
                "--chart-dirs",
                str((helm_dir / "charts").relative_to(repo_root)),
                "--target-branch",
                target_branch,
            )
        except CalledProcessError as e:
            raise ClickException(f"list-changed failed with rc={e.returncode}") from e
        charts = [line.strip() for line in out.splitlines() if line.strip()]
        click.echo(json.dumps(charts))
