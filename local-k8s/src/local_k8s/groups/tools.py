import click

from local_k8s.commands.tools.install import install


@click.group("tools", help="Manage k8s tooling")
def tools() -> None:
    pass


tools.add_command(install)
