from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

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
from agent_diagrams.renderers import images

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


# ── Mermaid internal helpers ──


def test_node_id_sanitization():
    assert _node_id("aws:vpc:vpc-1") == "aws_vpc_vpc_1"


def test_node_id_leading_digit():
    assert _node_id("123-abc").startswith("n_")


def test_node_id_empty():
    assert _node_id("") == "node"


@pytest.mark.parametrize("reserved", ["graph", "end", "subgraph", "CLASS"])
def test_node_id_mermaid_reserved_word(reserved):
    assert _node_id(reserved).startswith("n_")


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


# ── Mermaid image runtime coverage ──


def test_resolve_container_engine_prefers_docker(monkeypatch):
    monkeypatch.setattr(images.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert images._resolve_container_engine("auto") == "docker"


def test_resolve_container_engine_falls_back_to_podman(monkeypatch):
    monkeypatch.setattr(
        images.shutil,
        "which",
        lambda name: "/usr/bin/podman" if name == "podman" else None,
    )
    assert images._resolve_container_engine("auto") == "podman"


def test_native_mermaid_command(monkeypatch, tmp_path):
    monkeypatch.setattr(images.shutil, "which", lambda name: "/usr/bin/mmdc" if name == "mmdc" else None)
    monkeypatch.setenv("MERMAID_PUPPETEER_CONFIG", "/etc/puppeteer.json")
    captured = []
    monkeypatch.setattr(images, "_run", lambda cmd: captured.append(cmd))

    source = tmp_path / "input.mmd"
    source.write_text("flowchart LR\n  a --> b\n")
    output = tmp_path / "output.svg"
    images.render_mermaid_image(source, output, runtime="native", theme="dark")

    assert captured == [[
        "mmdc",
        "-i",
        str(source),
        "-o",
        str(output),
        "-b",
        "transparent",
        "-t",
        "dark",
        "-p",
        "/etc/puppeteer.json",
    ]]


def test_podman_mermaid_command(monkeypatch, tmp_path):
    monkeypatch.setattr(images.shutil, "which", lambda name: "/usr/bin/podman" if name == "podman" else None)
    monkeypatch.setattr(images, "_host_user", lambda: (1234, 5678))
    captured = []
    monkeypatch.setattr(images, "_run", lambda cmd: captured.append(cmd))

    source = tmp_path / "input.mmd"
    source.write_text("flowchart LR\n  a --> b\n")
    output = tmp_path / "output.png"
    images.render_mermaid_image(
        source,
        output,
        runtime="container",
        container_engine="podman",
    )

    cmd = captured[0]
    assert cmd[:4] == ["podman", "run", "--rm", "--userns=keep-id"]
    assert ["-u", "1234:5678"] == cmd[4:6]
    assert f"{tmp_path}:/data:Z" in cmd


def test_run_reports_missing_executable(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(images.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="executable: podman"):
        images._run(["podman", "run"])


def test_run_reports_failed_command(monkeypatch):
    result = subprocess.CompletedProcess(["podman", "run"], 125, "out", "err")
    monkeypatch.setattr(images.subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(RuntimeError, match="exit_code: 125"):
        images._run(["podman", "run"])
