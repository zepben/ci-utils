from ci_utils import Environment
from ci_utils.utils.version import VersionUtils

from test_utils.configs import configs

import os
import pytest
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


def test_validate_version():
    cs_config = configs["csharp"]
    test_file = create_test_file(cs_config)
    utils = VersionUtils(ctx, "csharp", test_file)
    assert utils.version == cs_config.current_version
    assert utils.sem_version == cs_config.current_version.split("-")[0]

    utils.validate_version(utils.version)
    with pytest.raises(Exception):
        utils.validate_version(f"{utils.version}.33")


def test_increment_version():
    cs_config = configs["csharp"]
    test_file = create_test_file(cs_config)
    utils = VersionUtils(ctx, "csharp", test_file)
    assert utils.version == cs_config.current_version
    assert utils.sem_version == cs_config.current_version.split("-")[0]
    # patch +1 the third number
    utils.increment_version("patch")
    new_version = cs_config.current_version.split("-")[0].split(".")
    assert utils.new_version == f"{new_version[0]}.{new_version[1]}.{int(new_version[2])+1}"

    # minor +1 the second number and resets the third
    utils.increment_version("minor")
    new_version = cs_config.current_version.split("-")[0].split(".")
    assert utils.new_version == f"{new_version[0]}.{int(new_version[1])+1}.0"

    # minor +1 the first number and resets the rest
    utils.increment_version("major")
    assert utils.new_version == "1.0.0"


def test_update_csproj_snapshot_version():
    cs_config = configs["csharp"]
    test_file = create_test_file(cs_config)
    utils = VersionUtils(ctx, "csharp", test_file)
    # Update the pre$ version and write the file
    utils.update_snapshot_version()
    # now fetch it and check the version was updated
    version, sem_version = utils.lang_utils.parse_project_version(test_file)
    assert version == cs_config.next_snapshot
    assert sem_version == cs_config.current_version.split("-")[0]


def test_update_js_snapshot_version():
    js_config = configs["js"]
    test_file = create_test_file(js_config)
    utils = VersionUtils(ctx, "js", test_file)
    # Update the next$ version and write the file
    utils.update_snapshot_version()
    # now fetch it and check the version was updated
    version, sem_version = utils.lang_utils.parse_project_version(test_file)
    assert version == js_config.next_snapshot
    assert sem_version == js_config.current_version.split("-")[0]


def test_update_jvm_snapshot_version():
    jvm_config = configs["jvm"]
    test_file = create_test_file(jvm_config)
    utils = VersionUtils(ctx, "jvm", test_file)
    # Update the SNAPSHOT$ version and write the file
    utils.update_snapshot_version()
    # now fetch it and check the version was updated
    version, sem_version = utils.lang_utils.parse_project_version(test_file)
    assert version == jvm_config.next_snapshot
    assert sem_version == jvm_config.current_version.split("-")[0]


def test_update_python_snapshot_version():
    python_config = configs["python"]
    test_file = create_test_file(python_config)
    utils = VersionUtils(ctx, "python", test_file)
    # Update the b$ version and write the file
    utils.update_snapshot_version()
    # now fetch it and check the version was updated
    version, sem_version = utils.lang_utils.parse_project_version(test_file)
    assert version == python_config.next_snapshot
    assert sem_version == python_config.current_version.split("b")[0]
