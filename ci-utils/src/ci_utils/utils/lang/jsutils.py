import json

from ci_utils.utils.lang.base import BaseUtils


class JsUtils(BaseUtils):
    version_regex = r"(?P<base>.*)-next(?P<beta>\d+)"

    @staticmethod
    def _version_string(base: str, beta: int):
        return f"{base}-next{beta}"

    def write_new_version(self, project_file: str, old: str, new: str):
        if old != new:
            self.ctx.info(f"Updating old version '{old}' to new version '{new}'")

            with open(project_file) as f:
                project = json.load(f)
                project["version"] = new

            with open(project_file, "w") as f:
                json.dump(project, f, indent=2)

    def parse_project_version(self, project_file: str) -> tuple[str, str]:
        with open(project_file) as f:
            project = json.load(f)
            project_version = project.get("version", None)
            if not project_version:
                self.ctx.fail("Err in JS parsing version")

            return project_version, project_version.split("-")[0]
