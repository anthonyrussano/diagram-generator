from __future__ import annotations

import json

import pytest

from agent_diagrams.cli import _apply_review_bundle, build_parser
from agent_diagrams.model import Edge, GraphData, Node
from agent_diagrams.renderers.ferroprint import render_ferroprint


def graph() -> GraphData:
    return GraphData(
        nodes=[
            Node(id="database:1", kind="database", label="Database", source="test"),
            Node(id="api/1", kind="service", label="API", source="test", attrs={"secret": "do-not-export"}),
            Node(id="caller", kind="user", label="客户", source="test"),
        ],
        edges=[
            Edge(src="caller", dst="api/1", rel="HTTPS", source="test"),
            Edge(src="api/1", dst="database:1", rel="query", source="test"),
        ],
        metadata={"token": "never-export-this"},
    )


def test_ferroprint_project_export_is_deterministic_editable_and_redacted(tmp_path):
    first = tmp_path / "first.ferroprint.json"
    second = tmp_path / "second.ferroprint.json"
    source = graph()
    render_ferroprint(source, first, name="Account", direction="LR")
    render_ferroprint(source, second, name="Account", direction="LR")
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["meta"]["project"] == "Account"
    assert payload["active"] == "s1"
    sheet = payload["sheets"][0]
    assert len(sheet["nodes"]) == 3
    assert len(sheet["edges"]) == 2
    assert {node["type"] for node in sheet["nodes"]} == {"actor", "service", "database"}
    assert {edge["label"] for edge in sheet["edges"]} == {"HTTPS", "query"}
    assert all(edge["from"] != edge["to"] for edge in sheet["edges"])
    assert {n["id"] for n in sheet["nodes"]}.isdisjoint({e["id"] for e in sheet["edges"]})
    assert "客户" in first.read_text()
    assert "do-not-export" not in first.read_text()
    assert "never-export-this" not in first.read_text()


def test_ferroprint_layout_keeps_connections_and_direction(tmp_path):
    base = graph()
    render_ferroprint(base, tmp_path / "lr.json", direction="LR")
    render_ferroprint(base, tmp_path / "tb.json", direction="TB")
    lr = json.loads((tmp_path / "lr.json").read_text())["sheets"][0]["nodes"]
    tb = json.loads((tmp_path / "tb.json").read_text())["sheets"][0]["nodes"]
    lrpos = {n["label"]: (n["x"], n["y"]) for n in lr}
    tbpos = {n["label"]: (n["x"], n["y"]) for n in tb}
    assert lrpos["客户"][0] < lrpos["API"][0] < lrpos["Database"][0]
    assert tbpos["客户"][1] < tbpos["API"][1] < tbpos["Database"][1]


def test_ferroprint_cycle_keeps_edges(tmp_path):
    data = GraphData(
        nodes=[Node(id=n, kind="service", label=n, source="test") for n in ("a", "b")],
        edges=[
            Edge(src="a", dst="b", rel="go", source="test"),
            Edge(src="b", dst="a", rel="retry", source="test"),
        ],
    )
    render_ferroprint(data, tmp_path / "cycle.json")
    payload = json.loads((tmp_path / "cycle.json").read_text())
    assert len(payload["sheets"][0]["edges"]) == 2


def test_ferroprint_rejects_unrepresentable_edges(tmp_path):
    data = graph()
    data.edges.append(Edge(src="missing", dst="api/1", rel="unknown", source="test"))
    with pytest.raises(ValueError, match="missing endpoint"):
        render_ferroprint(data, tmp_path / "out.json")
    assert not (tmp_path / "out.json").exists()

    data = graph()
    data.edges.append(Edge(src="api/1", dst="api/1", rel="loop", source="test"))
    with pytest.raises(ValueError, match="self-loops"):
        render_ferroprint(data, tmp_path / "out.json")


def test_review_bundle_includes_ferroprint():
    args = build_parser().parse_args(["--review-bundle"])
    _apply_review_bundle(args)
    assert args.ferroprint is True
    assert args.zip_artifacts is True
    assert "drawio" in args.diagram_format


def test_ferroprint_can_be_requested_independently():
    args = build_parser().parse_args(["--ferroprint"])
    assert args.ferroprint is True
    assert args.diagram_format is None
    assert args.zip_artifacts is False
