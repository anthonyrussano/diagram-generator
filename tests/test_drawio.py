from __future__ import annotations

import importlib.util
import shutil
import xml.etree.ElementTree as ET

import pytest

from agent_diagrams.model import Edge, GraphData, Node
from agent_diagrams.renderers.diagrams_renderer import render_with_diagrams
from agent_diagrams.renderers.drawio import export_dot_to_drawio
from agent_diagrams.spec_workflows import render_spec_diagram

pytestmark = pytest.mark.skipif(
    not shutil.which("dot") or importlib.util.find_spec("diagrams") is None,
    reason="Graphviz and the render extra required",
)


def cells(path):
    return ET.parse(path).findall(".//mxCell")


def test_drawio_preserves_nested_groups_labels_and_connector_directions(tmp_path):
    dot = tmp_path / "test.dot"
    dot.write_text("""digraph {
      label="Architecture";
      subgraph cluster_outer {
        label="Outer";
        subgraph cluster_inner { label="Inner"; a [label="API & worker"]; }
        b [label="Database"];
      }
      c [label="Outside"];
      a -> b [label="writes", color="#ff0000", style=dashed, dir=both];
      b -> c [dir=none];
    }""")
    path = export_dot_to_drawio(dot, tmp_path / "diagram.drawio")
    elements = cells(path)
    vertices = {
        cell.get("value"): cell for cell in elements if cell.get("vertex") == "1"
    }
    assert set(vertices) == {"Outer", "Inner", "API & worker", "Database", "Outside"}
    assert vertices["Inner"].get("parent") == vertices["Outer"].get("id")
    assert vertices["API & worker"].get("parent") == vertices["Inner"].get("id")
    assert vertices["Database"].get("parent") == vertices["Outer"].get("id")
    assert vertices["Outside"].get("parent") == "1"
    edges = [cell for cell in elements if cell.get("edge") == "1"]
    assert len(edges) == 2
    assert "endArrow=classic" in edges[0].get("style")
    assert "startArrow=classic" in edges[0].get("style")
    assert "dashed=1" in edges[0].get("style")
    assert "endArrow=none" in edges[1].get("style")
    for vertex in vertices.values():
        assert float(vertex.find("mxGeometry").get("width")) > 0


def test_collected_graph_exports_editable_cells_and_embedded_icons(tmp_path):
    graph = GraphData(
        nodes=[
            Node("web", "Web", "aws.ec2", "json"),
            Node("db", "DB", "aws.rds", "json"),
        ],
        edges=[Edge("web", "db", "queries", "json")],
    )
    first = render_with_diagrams(graph, tmp_path / "first", output_format="drawio")
    second = render_with_diagrams(graph, tmp_path / "second", output_format="drawio")
    assert first.read_bytes() == second.read_bytes()
    elements = cells(first)
    assert len([cell for cell in elements if cell.get("vertex")]) == 2
    assert len([cell for cell in elements if cell.get("edge")]) == 1
    assert all(
        "image=data:image/png," in cell.get("style")
        for cell in elements
        if cell.get("vertex")
    )
    assert str(tmp_path) not in first.read_text()


def test_spec_drawio_has_editable_groups_and_semantic_edges(tmp_path):
    spec = {
        "title": "Spec",
        "clusters": [{"id": "app", "label": "Application"}],
        "nodes": [
            {"id": "a", "label": "API", "cluster": "app"},
            {"id": "b", "label": "Store"},
        ],
        "edges": [{"from": "a", "to": "b", "label": "reads"}],
    }
    path = render_spec_diagram(spec, tmp_path / "spec", output_format="drawio")
    elements = cells(path)
    assert {cell.get("value") for cell in elements if cell.get("vertex")} == {
        "Application",
        "API",
        "Store",
    }
    assert [cell.get("value") for cell in elements if cell.get("edge")] == ["reads"]


def test_missing_graphviz_and_layout_errors_are_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError, match="Graphviz 'dot'"):
        export_dot_to_drawio(tmp_path / "missing.dot", tmp_path / "missing.drawio")


def test_orthogonal_routes_and_invisible_layout_cells(tmp_path):
    dot = tmp_path / "layout.dot"
    dot.write_text("""digraph {
      graph [splines=ortho, rankdir=LR, nodesep=1.0];
      subgraph cluster_hidden { style=invis; a [label="API"]; }
      b [label="Worker"];
      c [label="Store"];
      anchor [style=invis];
      { rank=same; b; c; }
      a:e -> b:w;
      a:e -> c:w;
      b -> c;
      c -> anchor [style=invis];
    }""")
    path = export_dot_to_drawio(dot, tmp_path / "layout.drawio")
    elements = cells(path)
    vertices = [cell for cell in elements if cell.get("vertex")]
    assert {cell.get("value") for cell in vertices} == {"API", "Worker", "Store"}
    ids = {cell.get("id") for cell in elements}
    assert all(cell.get("parent") in ids for cell in elements if cell.get("parent"))
    assert ET.parse(path).findall(".//Array[@as='points']/mxPoint")
