import os
import click

from ci_utils import pass_environment

cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "commands"))


class ComplexCLI(click.Group):
    def list_commands(self, ctx):
        rv = []
        for filename in os.listdir(cmd_folder):
            if filename.endswith(".py") and filename.startswith("cmd_"):
                cmd = filename[4:-3].replace('_', '-')
                rv.append(cmd)
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        try:
            mod = __import__(f"ci_utils.commands.cmd_{name.replace('-', '_')}", None, None, ["cli"])
        except ImportError:
            return
        return mod.cli


@click.command(cls=ComplexCLI)
@click.option("-v", "--version", is_flag=True, help="Show version")
@pass_environment
def cli(ctx, version):
    """Zepben CI utilities"""
