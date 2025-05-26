import re
import xml.etree.ElementTree as ET

from ci_utils.utils.lang.base import BaseUtils


class JvmUtils(BaseUtils):
    version_regex = r"(?P<base>.*)-SNAPSHOT(?P<beta>\d+)"

    @staticmethod
    def _version_string(base: str, beta: int):
        return f'{base}-SNAPSHOT{beta}'

    def write_new_version(self, project_file: str, old: str, new: str):
        if old != new:
            self.ctx.info(f"Updating old version '{old}' to new version '{new}'")
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)) 
            tree = ET.parse(project_file, parser)
            root = tree.getroot()

            # now find the project and namespace
            m = re.search(r".*{(?P<ns>http://.*)}.*", root.tag)
            ns = m.group("ns")

            # Register the namespace for the writing out
            ET.register_namespace('', ns)
            version_elem = root.find("./version", namespaces={'': ns})
            if version_elem is not None and version_elem.text == old:
                version_elem.text = new
                tree.write(project_file, short_empty_elements=False, encoding="utf-8", xml_declaration=True)

    def parse_project_version(self, project_file: str) -> tuple[str, str]:
        if not project_file.endswith(".xml"):
            self.ctx.fail("Project file for java projects should be in POM XML format")

        version: str = ""
        sem_version: str = ""
        ns: str = ""

        tree = ET.parse(project_file)
        root = tree.getroot()

        # now find the project and namespace
        m = re.search(r".*{(?P<ns>http://.*)}.*", root.tag)
        if m is not None:
            ns = m.group("ns")

            # Register the namespace for the writing out
            ET.register_namespace('', ns)
            version_elem = root.find("./version", namespaces={'': ns})
            if version_elem is not None:
                version = version_elem.text
                sem_version = version.split('-')[0]
            else:
                self.ctx.fail(f"Error parsing version in {project_file}, either none found or too many")
        else:
            self.ctx.fail(
                f"Couldn't find project in {project_file}. Project is XML namespace, and for POM it's expected to be something like 'http://maven.apache.org/POM/4.0.0'")

        return version, sem_version
