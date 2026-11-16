from pathlib import Path

import yaml

from tests.support.execution import ExecuteHook, FakeExecute, option_value


def write_chart(chart_dir: Path, chart_yaml: dict[str, object]) -> Path:
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_yaml))
    return chart_dir


def _pulled_reference(args: tuple[str, ...]) -> str:
    return args[args.index("pull") + 1]


def pulled_charts(fake: FakeExecute) -> dict[str, str]:
    """Version requested for each OCI reference the fake saw `helm pull`."""
    return {
        _pulled_reference(entry.args): option_value(entry.args, "--version")
        for entry in fake.calls_for("helm", "pull")
    }


def pulls_published_chart(annotations: dict[str, str] | None = None) -> ExecuteHook:
    """Hook for `helm pull --untar`: untars the chart named by the OCI reference.

    Like helm, the chart lands in a directory named after the chart under
    --destination, and its Chart.yaml is what zep-dev reads.
    """

    def pull(args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        name = _pulled_reference(args).rsplit("/", 1)[-1]
        write_chart(
            Path(option_value(args, "--destination")) / name,
            {
                "name": name,
                "version": option_value(args, "--version"),
                "annotations": annotations or {},
            },
        )

    return pull
