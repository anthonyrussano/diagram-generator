from __future__ import annotations

from agent_diagrams.cli import (
    COMPOSITE_COMMANDS,
    _merge_graphs,
    build_composite_parser,
    build_parser,
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
    args = parser.parse_args(["--svg", "--png", "--diagram-format", "svg"])
    assert args.svg is True
    assert args.png is True
    assert args.diagram_format == ["svg"]


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
    assert args.format == "png"


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
    assert COMPOSITE_COMMANDS == {"spec", "compare", "k8s", "aws-boto3"}


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
