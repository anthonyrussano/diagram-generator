from __future__ import annotations

import importlib.util
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile

import pytest

from agent_diagrams.cli import main

pytestmark = pytest.mark.skipif(
    not shutil.which("dot") or importlib.util.find_spec("diagrams") is None,
    reason="Graphviz and the render extra required",
)


def test_discovered_hcl_drawio_and_warnings_are_in_bundle(
    tmp_path, monkeypatch, capsys
):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "main.tf").write_text("""
resource "aws_vpc" "main" {}
resource "aws_instance" "web" {
  vpc_id = aws_vpc.main.id
  depends_on = [aws_subnet.missing]
}
""")
    outputs = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            "diagram-gen",
            "--discover",
            "--root",
            str(inputs),
            "--out-dir",
            str(outputs),
            "--name",
            "infra",
            "--diagram-format",
            "drawio",
            "--artifact-folder",
            "--zip-artifacts",
        ],
    )
    main()
    assert "Nodes: 2 | Edges: 1" in capsys.readouterr().out
    directory = outputs / "infra"
    assert ET.parse(directory / "infra.diagram.drawio").findall(".//mxCell[@edge='1']")
    warnings = json.loads((directory / "infra.blindspots.json").read_text())["warnings"]
    assert any("aws_subnet.missing" in warning for warning in warnings)
    with zipfile.ZipFile(outputs / "infra.zip") as archive:
        assert {
            "infra.diagram.drawio",
            "infra.diagram.dot",
            "infra.blindspots.json",
            "infra.blindspots.md",
        } <= set(archive.namelist())


def test_python_cli_renders_and_prints_graph_counts(tmp_path, monkeypatch, capsys):
    script = tmp_path / "architecture.py"
    script.write_text("""from diagrams import Diagram, Node
with Diagram("Example"):
    Node("API") >> Node("Database")
""")
    monkeypatch.setattr(
        "sys.argv",
        [
            "diagram-gen",
            "python",
            "--script",
            str(script),
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "drawio",
        ],
    )
    main()
    assert "Nodes: 2 | Edges: 1" in capsys.readouterr().out
    assert (tmp_path / "out" / "architecture.drawio").is_file()
