from pathlib import Path

from local_k8s.models import RequiredTool

TOOLS: list[RequiredTool] = [
    RequiredTool(
        name="helm",
        version="v4.2.2",
        url="https://get.helm.sh/helm-{version}-linux-amd64.tar.gz",
        archive_member="linux-amd64/helm",
    ),
    RequiredTool(
        name="ct",
        version="3.14.0",
        url=(
            "https://github.com/helm/chart-testing/releases/download/"
            "v{version}/chart-testing_{version}_linux_amd64.tar.gz"
        ),
        archive_member="ct",
    ),
    RequiredTool(
        name="kubeconform",
        version="v0.8.0",
        url=(
            "https://github.com/yannh/kubeconform/releases/download/"
            "{version}/kubeconform-linux-amd64.tar.gz"
        ),
        archive_member="kubeconform",
    ),
    RequiredTool(
        name="kind",
        version="v0.32.0",
        url="https://kind.sigs.k8s.io/dl/{version}/kind-linux-amd64",
    ),
    RequiredTool(
        name="kubectl",
        version="v1.36.2",
        url="https://dl.k8s.io/release/{version}/bin/linux/amd64/kubectl",
    ),
    RequiredTool(
        name="shellcheck",
        version="v0.11.0",
        url=(
            "https://github.com/koalaman/shellcheck/releases/download/"
            "{version}/shellcheck-{version}.linux.x86_64.tar.gz"
        ),
        archive_member="shellcheck-{version}/shellcheck",
    ),
]
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}

# The files should live relative to helm dir in Application repo
CT_YAML = Path("ct.yaml")
CI_SECRETS_YAML = Path("ci-secrets.yaml")
