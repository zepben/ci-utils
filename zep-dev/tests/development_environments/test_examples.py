"""The worked example and documentation snippets remain valid."""

from io import StringIO
from pathlib import Path

from tests.support.fixtures import WriteBindings
from tests.support.paths import PROJECT_ROOT
from zep_dev.development_environments.bindings import Bindings
from zep_dev.development_environments.documents import (
    load_template,
    load_yaml,
    read_mapping,
)
from zep_dev.development_environments.local_inputs import (
    load_bindings,
    resolve_inputs,
)
from zep_dev.development_environments.manifests import resolve_application_manifests
from zep_dev.development_environments.templates import (
    EnvironmentTemplate,
    TemplateInputs,
)
from zep_dev.infrastructure.serialization import string_mapping

EXAMPLES = PROJECT_ROOT / "examples"


def documentation_yaml(path: Path, heading: str) -> list[dict[str, object]]:
    section = path.read_text(encoding="utf-8").split(f"{heading}\n", 1)[1]
    section = section.split("\n## ", 1)[0].split("\n### ", 1)[0]
    return [
        string_mapping(load_yaml(StringIO(block.split("\n```", 1)[0])), str(path))
        for block in section.split("```yaml\n")[1:]
    ]


def test_integration_example_resolves_inputs_and_validates_manifests(
    tmp_path: Path,
    deployments_checkout: Path,
    write_bindings: WriteBindings,
) -> None:
    data = tmp_path / "network"
    data.mkdir()
    body = read_mapping(EXAMPLES / "bindings.yaml")
    mounts = string_mapping(body["mounts"], "example mounts")
    repositories = string_mapping(body["repositories"], "example repositories")
    mounts["ewb-data"] = str(data)
    repositories["deployments"] = str(deployments_checkout)
    write_bindings(mounts=mounts, repositories=repositories)
    path = EXAMPLES / "integration" / "template.yaml"

    template, distribution = load_template(path)
    inputs = resolve_inputs(template, load_bindings(required=True))
    manifests = resolve_application_manifests(path, template, template.metadata.name)

    assert distribution is not None
    assert set(distribution.charts) == {"ewb", "eas", "eas-web-client"}
    assert inputs.mounts == {"ewb-data": data}
    assert inputs.repositories == {"deployments": deployments_checkout}
    assert inputs.secrets == {}
    assert manifests


def test_readme_minimal_template_needs_no_inputs() -> None:
    (body,) = documentation_yaml(
        PROJECT_ROOT / "README.md", "## Create and use an Environment"
    )
    template = EnvironmentTemplate.model_validate(body)
    inputs = resolve_inputs(template, Bindings())

    assert template.metadata.name == "minimal"
    assert template.distribution is None
    assert template.services == {}
    assert inputs.mounts == {}
    assert inputs.repositories == {}
    assert inputs.secrets == {}


def test_reference_argo_template_consumes_repository(
    deployments_checkout: Path,
) -> None:
    (body,) = documentation_yaml(
        PROJECT_ROOT / "docs/reference.md", "## Argo repository setup"
    )
    template = EnvironmentTemplate.model_validate(body)
    bindings = Bindings(repositories={"deployments": deployments_checkout})
    inputs = resolve_inputs(template, bindings)

    assert template.distribution is None
    assert template.applications == {}
    assert any(node.role == "worker" for node in template.cluster.kind.nodes)
    assert inputs.repositories == {"deployments": deployments_checkout}
    assert inputs.argo_repositories == {"deployments": deployments_checkout}


def test_reference_secret_source_syntax() -> None:
    template_body, bindings_body = documentation_yaml(
        PROJECT_ROOT / "docs/reference.md", "### Secret sources"
    )
    inputs = TemplateInputs.model_validate(template_body["inputs"])
    bindings = Bindings.model_validate(bindings_body)

    assert set(inputs.secrets) == set(bindings.secrets)
    assert bindings.secrets["app-credentials"].env == "APP_CREDENTIALS"
    assert bindings.secrets["other-credentials"].file == Path(
        "/home/alice/secrets/other.env"
    )
