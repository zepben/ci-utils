from pathlib import Path
from typing import assert_never

import click

from zep_dev.runtime_contract import (
    PinOutcome,
    pin_runtime_contract,
    read_applications,
)

TERRAFORM_DEPLOYMENTS = Path("terraform/deployments")


@click.command("pin")
@click.option(
    "--check",
    is_flag=True,
    help="Change nothing; fail if a Terraform root does not pin the contract its chart needs.",
)
@click.argument(
    "paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
def pin(check: bool, paths: tuple[Path, ...]) -> None:
    """Pin each Application's Terraform root to the runtime contract its chart needs.

    A released chart names the runtime contract commit it needs in its
    zepben.com/runtime-contract-ref annotation. The Argo CD Application names the
    Terraform root that applies the contract in its zepben.com/terraform-root
    annotation. The root pins the commit as the <chart>_runtime_contract_ref local
    in runtime-contracts.tf.json.

    PATHS are Application files, or directories searched for Applications with a
    zepben.com/terraform-root annotation.
    """
    outdated = 0
    for application in read_applications(list(paths)):
        for chart in application.charts:
            outcome = pin_runtime_contract(application, chart, check=check)
            label = f"{application.name}: {chart.name} {chart.version}"
            click.echo(f"{label}: {describe(outcome)}")
            if outcome is not None and outcome.status == "outdated":
                outdated += 1
    if outdated:
        raise click.ClickException(
            f"{outdated} Terraform root pin(s) out of date; "
            "run zep-dev runtime-contract pin, then apply the printed roots"
        )


def describe(outcome: PinOutcome | None) -> str:
    if outcome is None:
        return "no runtime contract"
    match outcome.status:
        case "already_pinned":
            return f"runtime contract {outcome.ref} already pinned"
        case "outdated":
            pinned = outcome.previous or "none"
            return f"needs runtime contract {outcome.ref}, {outcome.root} pins {pinned}"
        case "pinned":
            lines = [f"pinned runtime contract {outcome.ref} in {outcome.root}"]
            if outcome.source is not None and outcome.previous is not None:
                compare = f"{outcome.source}/compare/{outcome.previous}...{outcome.ref}"
                lines.append(f"  changes: {compare}")
            lines.append(f"  apply: {apply_command(outcome.root)}")
            return "\n".join(lines)
        case _:
            assert_never(outcome.status)


def apply_command(root: Path) -> str:
    if root.is_relative_to(TERRAFORM_DEPLOYMENTS):
        deployment = root.relative_to(TERRAFORM_DEPLOYMENTS)
        return f"cd terraform && ./terraform.sh -d {deployment} apply"
    return f"terraform -chdir={root} apply"
