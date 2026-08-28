import click

from zep_dev.commands.terraform.commands import apply, destroy


@click.group("terraform", help="Manage Terraform resources in local Kubernetes")
def terraform() -> None:
    pass


terraform.add_command(apply)
terraform.add_command(destroy)
