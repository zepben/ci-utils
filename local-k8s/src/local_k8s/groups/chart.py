import click

from zep_dev.commands.chart.lint import lint
from zep_dev.commands.chart.list_changed import list_changed
from zep_dev.commands.chart.metadata import metadata
from zep_dev.commands.chart.push import push
from zep_dev.commands.chart.release_notes import release_notes
from zep_dev.commands.chart.test import test


@click.group("chart", help="Helm chart lint, test, and publish commands")
def chart() -> None:
    pass


chart.add_command(metadata)
chart.add_command(list_changed)
chart.add_command(lint)
chart.add_command(push)
chart.add_command(release_notes)
chart.add_command(test)
