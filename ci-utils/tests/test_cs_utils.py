from ci_utils import Environment
import os
from ci_utils.utils.lang.csutils import CsUtils
from test_utils.configs import configs
from jinja2 import Environment as JEnv, FileSystemLoader

ctx = Environment()
environment = JEnv(loader=FileSystemLoader(
    os.path.join(os.path.dirname(__file__), "test_files")))

def create_test_file(config):
    template = environment.get_template(config.project_file)
    content = template.render(current_version=config.current_version)
    fpath = os.path.join("/tmp", config.project_file)
    with open(fpath, "w") as f:
        f.write(content)
    return fpath


def test_cs_parse_version_cproj():
    config = configs["csharp"]
    test_file = create_test_file(config)
    version, sem_version = CsUtils(ctx).parse_project_version(test_file)
    assert version == config.current_version
    assert sem_version == config.current_version.split("-")[0]


def test_cs_parse_version_nuspec():
    test_file = "/".join((os.path.dirname(__file__), "test_files/test.nuspec"))
    version, sem_version = CsUtils(ctx).parse_project_version(test_file)
    assert version == "0.26.0-pre3"
    assert sem_version == "0.26.0"


def test_cs_parse_version_assemblyinfo():
    test_file = "/".join((os.path.dirname(__file__), "test_files/AssemblyInfo.cs"))
    version, sem_version = CsUtils(ctx).parse_project_version(test_file)
    assert version == "2.5.39.4"
    assert sem_version == "2.5.39.4"
