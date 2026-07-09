import click

from local_k8s.commands.ct.lint_and_install import lint_and_install


@click.group("ct", help="Execute ct (chart testing) commands")
def ct() -> None:
    pass


ct.add_command(lint_and_install)
