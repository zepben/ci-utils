import re

from ci_utils.utils.lang.base import BaseUtils


class PyUtils(BaseUtils):
    version_regex = r"(?P<base>.*)b(?P<beta>\d+)"

    @staticmethod
    def _version_string(base: str, beta: str):
        return f'{base}b{beta}'

    def write_new_version(self, project_file: str, old: str, new: str):
        if old != new:

            self.ctx.info(f"Updating old version '{old}' to new version '{new}'")
            with open(project_file, "r") as p:
                text = re.sub(rf"version\s*=\s*\"{old}\"", f"version=\"{new}\"", p.read())

            # write it up to the file
            with open(project_file, "w") as p:
                p.write(text)

    def parse_project_version(self, project_file: str) -> tuple[str, str]:
        with open(project_file, "r") as f:
            text = f.read().split('\n')
            for line in text:
                found_version = re.search(r".*version\s*=\s*\"(?P<version>(?P<sem_version>[0-9]+\.[0-9]+\.[0-9]+)b[0-9]+)\"", line)
                if found_version is not None:
                    return found_version.group('version'), found_version.group('sem_version')

        # TODO: handle the fact that no version was parsed
        return "", ""
