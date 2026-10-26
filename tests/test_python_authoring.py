from __future__ import annotations

import importlib.util
import os
import shutil
import xml.etree.ElementTree as ET

import pytest

from agent_diagrams.icon_catalog import resolve_asset_path
from agent_diagrams.python_authoring import render_python_script

pytestmark = pytest.mark.skipif(
    not shutil.which("dot") or importlib.util.find_spec("diagrams") is None,
    reason="Graphviz and the render extra required",
)


def test_python_supports_helpers_loops_and_multiple_formats(tmp_path):
    (tmp_path / "helpers.py").write_text(
        'def labels():\n    return ["one", "two", "three"]\n'
    )
    script = tmp_path / "architecture.py"
    script.write_text("""from diagrams import Diagram, Cluster
from diagrams.aws.compute import EC2
from helpers import labels

with Diagram("Workers", show=True, filename="ignored"):
    with Cluster("Fleet"):
        workers = [EC2(label) for label in labels()]
    workers[0] >> workers[1] >> workers[2]
""")
    before = os.getcwd()
    result = render_python_script(
        script, tmp_path / "out'put" / "workers", formats=["png", "svg", "drawio"]
    )
    assert os.getcwd() == before
    assert result["diagrams"][0]["nodes"] == 3
    assert result["diagrams"][0]["edges"] == 2
    assert len(result["diagrams"][0]["paths"]) == 3
    assert not (tmp_path / "ignored.png").exists()
    drawio = tmp_path / "out'put" / "workers.drawio"
    vertices = ET.parse(drawio).findall(".//mxCell[@vertex='1']")
    assert {node.get("value") for node in vertices} == {"Fleet", "one", "two", "three"}


def test_python_multiple_diagrams_are_named_and_counted(tmp_path):
    script = tmp_path / "multiple.py"
    script.write_text("""from diagrams import Diagram
from diagrams.generic.blank import Blank
for name in ["First", "Second"]:
    with Diagram(name):
        Blank(name)
""")
    result = render_python_script(script, tmp_path / "result", formats=["drawio"])
    assert [item["nodes"] for item in result["diagrams"]] == [1, 1]
    assert (tmp_path / "result.drawio").is_file()
    assert (tmp_path / "result-2.drawio").is_file()


def test_python_timeout_and_errors_are_reported(tmp_path):
    script = tmp_path / "timeout.py"
    script.write_text("import time\ntime.sleep(10)\n")
    with pytest.raises(RuntimeError, match="timed out after 1 seconds"):
        render_python_script(script, tmp_path / "out", formats=["png"], timeout=1)
    script.write_text('raise RuntimeError("specific failure")\n')
    with pytest.raises(RuntimeError, match="specific failure"):
        render_python_script(script, tmp_path / "out", formats=["png"])
    script.write_text('print("no diagrams")\n')
    with pytest.raises(ValueError, match="did not create any Diagram"):
        render_python_script(script, tmp_path / "out", formats=["png"])


def test_python_custom_icon_paths_resolve_from_script_directory(tmp_path):
    asset = resolve_asset_path("asset:network-interface.png")
    assert asset is not None
    (tmp_path / "icon.png").write_bytes(asset.read_bytes())
    script = tmp_path / "custom.py"
    script.write_text("""from diagrams import Diagram
from diagrams.custom import Custom
with Diagram("Custom asset"):
    Custom("Device", "icon.png")
""")
    output = tmp_path / "nested" / "custom"
    result = render_python_script(script, output, formats=["png", "drawio"])
    assert result["diagrams"][0]["nodes"] == 1
    xml = output.with_suffix(".drawio").read_text()
    assert "image=data:image/png," in xml
