import re


class Params:
    lang: str
    tag: str
    current_version: str
    next_snapshot: str
    project_file: str
    changelog: str

    def __init__(self, lang, released_tag, current_version, next_snapshot, project_file, changelog):
        self.lang = lang
        self.released_tag = released_tag
        self.current_version = current_version
        self.next_snapshot = next_snapshot
        self.project_file = project_file
        self.changelog = changelog

    def version(self) -> str:
        v = re.search(r"(?P<version>[0-9]+\.[0-9]+\.[0-9]+).*", self.next_snapshot)
        return v.group("version") if v else ""


goodbranch = "good-branch"
configs: dict[str] = {
    "jvm": Params(
        lang="jvm",
        released_tag="0.17.0",
        current_version="0.17.1-SNAPSHOT5",
        next_snapshot="0.17.1-SNAPSHOT6",
        project_file="pom.xml",
        changelog="changelog-jvm.md",
    ),
    "python": Params(
        lang="python",
        released_tag="0.38.0",
        current_version="0.38.1b1",
        next_snapshot="0.38.1b2",
        project_file="setup.py",
        changelog="changelog-python.md",
    ),
    "js": Params(
        lang="js",
        released_tag="5.1.0",
        current_version="5.1.1-next1",
        next_snapshot="5.1.1-next2",
        project_file="test_package.json",
        changelog="changelog-js.md",
    ),
    "csharp": Params(
        lang="csharp",
        released_tag="0.26.0",
        current_version="0.26.1-pre3",
        next_snapshot="0.26.1-pre4",
        project_file="test.csproj",
        changelog="changelog-cs.md",
    ),
}
