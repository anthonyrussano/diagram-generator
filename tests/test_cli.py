from __future__ import annotations

import pytest

from agent_diagrams.cli import (
    COMPOSITE_COMMANDS,
    _merge_graphs,
    build_composite_parser,
    build_parser,
    run_spec_batch_mode,
    run_spec_mode,
)
from agent_diagrams.model import Edge, GraphData, Node


# ── Standard parser ──


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.profile == "default"
    assert args.region == "us-east-1"
    assert args.direction == "LR"
    assert args.out_dir == "output"
    assert args.name == "infra"
    assert args.source is None
    assert args.discover is False
    assert args.mermaid_runtime == "auto"
    assert args.container_engine == "auto"


def test_build_parser_sources():
    parser = build_parser()
    args = parser.parse_args(["--source", "aws", "--source", "json"])
    assert args.source == ["aws", "json"]


def test_build_parser_discover():
    parser = build_parser()
    args = parser.parse_args(["--discover", "--root", "/tmp"])
    assert args.discover is True
    assert args.root == "/tmp"


def test_build_parser_output_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--svg",
            "--png",
            "--diagram-format",
            "svg",
            "--mermaid-runtime",
            "container",
            "--container-engine",
            "podman",
        ]
    )
    assert args.svg is True
    assert args.png is True
    assert args.diagram_format == ["svg"]
    assert args.mermaid_runtime == "container"
    assert args.container_engine == "podman"


def test_build_parser_artifact_flags():
    parser = build_parser()
    args = parser.parse_args(["--artifact-folder", "--zip-artifacts"])
    assert args.artifact_folder is True
    assert args.zip_artifacts is True


# ── Composite parser ──


def test_composite_parser_spec():
    parser = build_composite_parser()
    args = parser.parse_args(["spec", "--spec", "arch.yaml"])
    assert args.command == "spec"
    assert args.spec == "arch.yaml"
    assert args.format is None
    assert args.check is False


def test_composite_parser_spec_multiple_formats():
    parser = build_composite_parser()
    args = parser.parse_args(
        ["spec", "--spec", "arch.yaml", "--format", "svg", "--format", "png", "--check"]
    )
    assert args.format == ["svg", "png"]
    assert args.check is True


def test_composite_parser_spec_batch():
    parser = build_composite_parser()
    args = parser.parse_args(
        ["spec-batch", "--spec-dir", "specs", "--recursive", "--format", "svg"]
    )
    assert args.command == "spec-batch"
    assert args.spec_dir == "specs"
    assert args.recursive is True
    assert args.format == ["svg"]


def test_composite_parser_icons():
    parser = build_composite_parser()
    args = parser.parse_args(["icons", "--provider", "programming", "--search", "python", "--json"])
    assert args.command == "icons"
    assert args.provider == "programming"
    assert args.search == "python"
    assert args.json is True


def test_composite_parser_compare_single_spec():
    parser = build_composite_parser()
    args = parser.parse_args(["compare", "--spec", "migration.yaml"])
    assert args.command == "compare"
    assert args.spec == "migration.yaml"


def test_composite_parser_compare_two_files():
    parser = build_composite_parser()
    args = parser.parse_args(["compare", "--current", "a.yaml", "--future", "b.yaml"])
    assert args.current == "a.yaml"
    assert args.future == "b.yaml"


def test_composite_parser_aws_boto3():
    parser = build_composite_parser()
    args = parser.parse_args(["aws-boto3", "--profile", "prod", "--region", "eu-west-1"])
    assert args.command == "aws-boto3"
    assert args.profile == "prod"
    assert args.region == "eu-west-1"
    assert args.format == "png"


def test_composite_parser_k8s_discover():
    parser = build_composite_parser()
    args = parser.parse_args(["k8s", "discover", "--namespace", "prod"])
    assert args.command == "k8s"
    assert args.k8s_command == "discover"
    assert args.namespace == "prod"


def test_composite_parser_k8s_annotate():
    parser = build_composite_parser()
    args = parser.parse_args(["k8s", "annotate", "--spec", "arch.yaml", "--namespaces", "ns1,ns2"])
    assert args.k8s_command == "annotate"
    assert args.namespaces == "ns1,ns2"


def test_composite_parser_k8s_summarize():
    parser = build_composite_parser()
    args = parser.parse_args(["k8s", "summarize", "--namespaces", "prod,staging"])
    assert args.k8s_command == "summarize"
    assert args.namespaces == "prod,staging"


# ── COMPOSITE_COMMANDS ──


def test_composite_commands_coverage():
    assert COMPOSITE_COMMANDS == {"spec", "spec-batch", "compare", "k8s", "aws-boto3", "icons"}


def test_run_spec_check_prints_counts_without_rendering(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "arch.yaml"
    spec.write_text("nodes:\n  - id: a\nedges: []\nclusters: []\n")
    args = build_composite_parser().parse_args(["spec", "--spec", str(spec), "--check"])
    monkeypatch.setattr(
        "agent_diagrams.cli.render_spec_diagram",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rendered during --check")),
    )

    run_spec_mode(args)

    output = capsys.readouterr().out
    assert "Nodes: 1 | Edges: 0 | Clusters: 0" in output


def test_run_spec_renders_each_requested_format_once(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "arch.yaml"
    spec.write_text("nodes:\n  - id: a\nedges: []\n")
    calls = []

    def fake_render(state_spec, output_prefix, *, output_format, direction):
        calls.append((output_prefix, output_format, direction))
        return output_prefix.with_suffix(f".{output_format}")

    monkeypatch.setattr("agent_diagrams.cli.render_spec_diagram", fake_render)
    args = build_composite_parser().parse_args(
        [
            "spec",
            "--spec",
            str(spec),
            "--out-dir",
            str(tmp_path / "out"),
            "--output",
            "arch",
            "--format",
            "svg",
            "--format",
            "png",
        ]
    )

    run_spec_mode(args)

    assert [call[1] for call in calls] == ["svg", "png"]
    assert "Diagram generated:" in capsys.readouterr().out


def test_run_spec_batch_preserves_relative_paths_and_reports_totals(tmp_path, monkeypatch, capsys):
    spec_root = tmp_path / "specs"
    nested = spec_root / "nested"
    nested.mkdir(parents=True)
    (spec_root / "one.yaml").write_text("nodes:\n  - id: a\nedges: []\n")
    (nested / "two.yml").write_text(
        "nodes:\n  - id: b\n  - id: c\nedges:\n  - from: b\n    to: c\n"
    )
    calls = []

    def fake_render(state_spec, output_prefix, *, output_format, direction):
        calls.append((output_prefix, output_format))
        return output_prefix.with_suffix(f".{output_format}")

    monkeypatch.setattr("agent_diagrams.cli.render_spec_diagram", fake_render)
    output_root = tmp_path / "rendered"
    args = build_composite_parser().parse_args(
        [
            "spec-batch",
            "--spec-dir",
            str(spec_root),
            "--recursive",
            "--out-dir",
            str(output_root),
            "--format",
            "svg",
            "--format",
            "png",
        ]
    )

    run_spec_batch_mode(args)

    assert len(calls) == 4
    assert (output_root / "one", "svg") in calls
    assert (output_root / "nested" / "two", "png") in calls
    assert "Specs: 2 | Nodes: 3 | Edges: 1 | Clusters: 0 | Artifacts: 4" in capsys.readouterr().out


def test_run_spec_batch_validates_every_spec_before_rendering(tmp_path, monkeypatch):
    spec_root = tmp_path / "specs"
    spec_root.mkdir()
    (spec_root / "a-valid.yaml").write_text("nodes:\n  - id: a\nedges: []\n")
    (spec_root / "z-invalid.yaml").write_text("nodes:\n  - id: a\n  - id: a\nedges: []\n")
    calls = []
    monkeypatch.setattr(
        "agent_diagrams.cli.render_spec_diagram",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    args = build_composite_parser().parse_args(
        ["spec-batch", "--spec-dir", str(spec_root), "--out-dir", str(tmp_path / "out")]
    )

    with pytest.raises(ValueError, match="Duplicate node"):
        run_spec_batch_mode(args)

    assert calls == []


def test_run_spec_batch_rejects_output_name_collisions(tmp_path):
    spec_root = tmp_path / "specs"
    spec_root.mkdir()
    content = "nodes:\n  - id: a\nedges: []\n"
    (spec_root / "same.yaml").write_text(content)
    (spec_root / "same.json").write_text('{"nodes": [{"id": "a"}], "edges": []}')
    args = build_composite_parser().parse_args(
        ["spec-batch", "--spec-dir", str(spec_root), "--check"]
    )

    with pytest.raises(ValueError, match="would both render"):
        run_spec_batch_mode(args)


# ── _merge_graphs ──


def test_merge_graphs_deduplication(simple_graph):
    merged = _merge_graphs([simple_graph, simple_graph])
    # Duplicates should be deduped
    assert len(merged.nodes) == len(simple_graph.nodes)
    assert len(merged.edges) == len(simple_graph.edges)


def test_merge_graphs_metadata():
    g1 = GraphData(metadata={"source": "aws"})
    g2 = GraphData(metadata={"source": "json"})
    merged = _merge_graphs([g1, g2])
    assert "sources" in merged.metadata
    assert len(merged.metadata["sources"]) == 2


def test_merge_graphs_combines_different():
    g1 = GraphData()
    g1.add_node(Node(id="a", label="A", kind="k", source="s1"))
    g2 = GraphData()
    g2.add_node(Node(id="b", label="B", kind="k", source="s2"))
    merged = _merge_graphs([g1, g2])
    assert len(merged.nodes) == 2
