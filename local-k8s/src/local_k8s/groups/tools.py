import click

from local_k8s.commands.tools.commands import install, uninstall


@click.group("tools", help="Manage k8s tooling")
def tools() -> None:
    pass


tools.add_command(install)
tools.add_command(uninstall)
