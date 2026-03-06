from __future__ import annotations

import json
from pathlib import Path

from agent_diagrams.model import Node, Edge, GraphData
from agent_diagrams.renderers.mermaid import (
    _escape_label,
    _escape_rel,
    _node_id,
    _stable_node_id_map,
    render_mermaid,
)
from agent_diagrams.renderers.json_renderer import render_json
from agent_diagrams.renderers.diagrams_renderer import ICON_ALIASES

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


# ── Mermaid internal helpers ──


def test_node_id_sanitization():
    assert _node_id("aws:vpc:vpc-1") == "aws_vpc_vpc_1"


def test_node_id_leading_digit():
    assert _node_id("123-abc").startswith("n_")


def test_node_id_empty():
    assert _node_id("") == "node"


def test_escape_label_quotes():
    assert _escape_label('say "hello"') == "say 'hello'"


def test_escape_label_newlines():
    assert _escape_label("line1\nline2") == "line1<br/>line2"


def test_escape_rel():
    assert _escape_rel("is\nrelated") == "is related"


def test_stable_node_id_map_deterministic(simple_graph):
    m1 = _stable_node_id_map(simple_graph)
    m2 = _stable_node_id_map(simple_graph)
    assert m1 == m2


def test_stable_node_id_no_collisions():
    g = GraphData()
    # These two IDs would both sanitize to "a_b"
    g.add_node(Node(id="a-b", label="A", kind="k", source="s"))
    g.add_node(Node(id="a.b", label="B", kind="k", source="s"))
    mapping = _stable_node_id_map(g)
    values = list(mapping.values())
    assert len(values) == len(set(values)), "collision detected in ID map"


# ── render_mermaid ──


def test_render_mermaid_output(simple_graph, tmp_path):
    out = tmp_path / "test.mmd"
    render_mermaid(simple_graph, out)
    content = out.read_text()
    assert content.startswith("flowchart LR")
    assert "VPC One" in content
    assert "-->|in|" in content


def test_render_mermaid_direction(simple_graph, tmp_path):
    out = tmp_path / "test.mmd"
    render_mermaid(simple_graph, out, direction="TB")
    content = out.read_text()
    assert content.startswith("flowchart TB")


def test_render_mermaid_snapshot(simple_graph, tmp_path):
    out = tmp_path / "test.mmd"
    render_mermaid(simple_graph, out, direction="LR")
    actual = out.read_text()
    golden_path = SNAPSHOTS_DIR / "simple_graph.mmd"
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual)
    golden = golden_path.read_text()
    assert actual == golden, "Mermaid output diverged from golden snapshot"


# ── render_json ──


def test_render_json_structure(simple_graph, tmp_path):
    out = tmp_path / "test.graph.json"
    render_json(simple_graph, out)
    data = json.loads(out.read_text())
    assert "metadata" in data
    assert "nodes" in data
    assert "edges" in data


def test_render_json_roundtrip(simple_graph, tmp_path):
    out = tmp_path / "test.graph.json"
    render_json(simple_graph, out)
    data = json.loads(out.read_text())
    assert len(data["nodes"]) == len(simple_graph.nodes)
    assert len(data["edges"]) == len(simple_graph.edges)
    for i, node in enumerate(simple_graph.nodes):
        assert data["nodes"][i]["id"] == node.id
        assert data["nodes"][i]["label"] == node.label


def test_render_json_snapshot(simple_graph, tmp_path):
    out = tmp_path / "test.graph.json"
    render_json(simple_graph, out)
    actual = out.read_text()
    golden_path = SNAPSHOTS_DIR / "simple_graph.graph.json"
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual)
    golden = golden_path.read_text()
    assert actual == golden, "JSON output diverged from golden snapshot"


# ── diagrams_renderer coverage ──


def test_icon_aliases_are_dotted_paths():
    for key, value in ICON_ALIASES.items():
        assert "." in value, f"Alias '{key}' maps to non-dotted path '{value}'"
