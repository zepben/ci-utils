"""Cluster diagnostics for failed Environment provisioning."""

from pathlib import Path
from tempfile import TemporaryDirectory

from zep_dev.development_environments.kubernetes import kubectl
from zep_dev.development_environments.target import ExecutionTarget


def take_debug_dump(target: ExecutionTarget) -> None:
    with TemporaryDirectory(prefix="zep-dev-debug-dump-") as directory:
        output = Path(directory)
        try:
            kubectl(
                target,
                "cluster-info",
                "dump",
                "--all-namespaces",
                "-o",
                "yaml",
                "--output-directory",
                str(output),
                timeout=60,
            )
        finally:
            for path in sorted(output.rglob("*")):
                if path.is_file() and path.suffix in {".yaml", ".txt"}:
                    print(f"--- {path.relative_to(output)} ---", flush=True)
                    print(path.read_text(errors="replace"), flush=True)
