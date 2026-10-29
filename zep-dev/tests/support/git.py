"""Git for test repositories, isolated from the developer's own configuration."""

import os
import subprocess
from pathlib import Path

# No global or system config (signing, hooks, default branch), and no inherited
# GIT_DIR or GIT_INDEX_FILE from a hook that may be running the tests.
ENVIRONMENT = {
    **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.org",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.org",
}


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=ENVIRONMENT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def init_repository(path: Path) -> Path:
    git("init", "-q", "--initial-branch=main", str(path))
    return path


def commit_all(repo: Path, message: str) -> str:
    """Stage everything, commit, and return the new HEAD."""
    git("add", "-A", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)
