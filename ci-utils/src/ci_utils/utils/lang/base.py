import re

from abc import abstractmethod


class BaseUtils:
    version_regex: str = r''

    def __init__(self, ctx):
        self.ctx = ctx

    @staticmethod
    @abstractmethod
    def _version_string(base: str, beta: int):
        raise NotImplemented

    def update_snapshot_version(self, version: str, project_file: str):
        v = re.search(self.version_regex, version)
        if not v:
            self.ctx.fail(
                f"Couldn't parse the version {version} in {project_file}")

        base = v.group("base")
        beta = (int(v.group("beta")) + 1)

        self.write_new_version(project_file, version, self._version_string(base, beta))

    @abstractmethod
    def write_new_version(self, project_file: str, old: str, new: str):
        raise NotImplemented

    @abstractmethod
    def parse_project_version(self, project_file: str) -> tuple[str, str]:
        raise NotImplemented
