import click

from zep_dev.commands.runtime_contract.pin import pin


@click.group(
    "runtime-contract", help="Pin Terraform roots to their charts' runtime contracts"
)
def runtime_contract() -> None:
    pass


runtime_contract.add_command(pin)
