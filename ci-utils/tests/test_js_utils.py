import os
import pytest

from ci_utils import Environment
from ci_utils.utils.lang.jsutils import JsUtils
from test_utils.configs import configs
from jinja2 import Environment as JEnv, FileSystemLoader

ctx = Environment()
environment = JEnv(loader=FileSystemLoader(
    os.path.join(os.path.dirname(__file__), "test_files")))

config = configs["js"]


@pytest.fixture
def test_path():
    template = environment.get_template(config.project_file)
    content = template.render(current_version=config.current_version)
    fpath = os.path.join("/tmp", config.project_file)
    with open(fpath, "w") as f:
        f.write(content)
    yield fpath


def test_js_parse_version(test_path):
    version, sem_version = JsUtils(ctx).parse_project_version(test_path)
    assert version == config.current_version
    assert sem_version == config.current_version.split("-")[0]


def test_js_update_snapshot_version(test_path):
    JsUtils(ctx).update_snapshot_version(config.current_version,
                                       test_path)

    # # now fetch it and check the version was updated
    version, sem_version = JsUtils(ctx).parse_project_version(
        test_path)
    assert version == config.next_snapshot
    assert sem_version == config.current_version.split("-")[0]
