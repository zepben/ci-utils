import re
import xml.etree.ElementTree as ET

from typing import Any
from ci_utils.utils.lang.base import BaseUtils


class CsUtils(BaseUtils):
    version_regex = r"(?P<base>.*)-pre(?P<beta>\d+)"

    @staticmethod
    def _version_string(base: str, beta: int):
        return f'{base}-pre{beta}'

    def update_snapshot_version(self, version: str, project_file: str):
        if not project_file.endswith(".csproj"):
            self.ctx.fail("Project file must be a csproj file! Cannot update the snapshot version")

        super().update_snapshot_version(version, project_file)

    def write_new_version(self, project_file: str, old: str, new: str):

        if old != new:
            self.ctx.info(f"Writing new version {new}")

            if project_file.endswith("csproj"):
                tree = ET.parse(project_file)
                root = tree.getroot()
                version_elem = root.find("./PropertyGroup/Version")
                if version_elem is not None and version_elem.text == old:
                    self.ctx.info(f"Found {old} version, updating to {new}")
                    version_elem.text = new
                else:
                    self.ctx.info("Did't find version!")

                # these turn "12.23.12.44-pre34" into "12.23.12.44.34"
                assembly = root.find("./PropertyGroup/AssemblyVersion")
                if assembly:
                    assembly.text = new.replace("-pre", ".")

                file_version = root.find("./PropertyGroup/FileVersion")
                if file_version:
                    file_version.text = new.replace("-pre", ".")

                # Save the changes
                tree.write(project_file, encoding="utf-8", xml_declaration=True)

            elif project_file.endswith(".nuspec"):
                # parse XML with comments included to keep the original content
                parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
                tree = ET.parse(project_file, parser)
                root = tree.getroot()

                # now find the project and namespace
                m = re.search(r".*{(?P<ns>http://.*)}.*", root.tag)
                ns = m.group("ns")

                # Register the namespace for the writing out
                ET.register_namespace('', ns)
                version_elem = root.find("./metadata/version", namespaces={'': ns})
                if version_elem and version_elem.text == old:
                    version_elem.text = new
                    tree.write(project_file, short_empty_elements=False, encoding="utf-8", xml_declaration=True)
            else:
                # sed -i "s/$old_ver/$new_ver/g" $file
                new_text = ""
                with open(project_file, "r") as f:
                    text = f.read() 
                    new_text = text.replace(old, new)

                with open(project_file, "w") as f:
                    f.write(new_text)

    def parse_project_version(self, project_file: str) -> tuple[str, str]:
        version: Any = None
        sem_version: Any = None

        if project_file.endswith(".csproj"):
            try:
                tree = ET.parse(project_file)
                root = tree.getroot()
                version = root.find("PropertyGroup").find("Version").text
                if version:
                    sem_version = version.split("-")[0]
            except Exception as err:
                self.ctx.fail(
                    f"Couldn't find the project version in the /Project/PropertyGroup/Version field in the {project_file}: {err}")

        elif project_file.endswith(".nuspec"):
            try:
                tree = ET.parse(project_file)
                root = tree.getroot()
                found_project = re.search(r".*(?P<project>{http://.*}).*", root.tag)
                if not found_project:
                    self.ctx.fail(f"Cannot find schema/project in the {project_file}")

                project = found_project.group("project")
                version = root.find(f"./{project}metadata/{project}version").text
                if version:
                    sem_version = version.split("-")[0]

            except Exception as err:
                self.ctx.fail(
                    f"Couldn't find the project version in the /project/metadata/version field in the {project_file}: {err}")

        elif project_file.endswith("AssemblyInfo.cs"):
            with open(project_file, "r") as f:
                lines = f.read().split('\n')
                for line in lines:
                    found_ver = re.search(
                        r".*AssemblyVersion\(\"(?P<version>[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\"\)", line)
                    if found_ver:
                        version = found_ver.group('version')
                        sem_version = version
                        break

        return version, sem_version
