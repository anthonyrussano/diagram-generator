#!/usr/bin/env python3
"""Unified diagram tool for AWS discovery and spec-driven architecture diagrams.

Modes:
- aws: fetch resources from AWS and generate a diagram (reuses aws_to_diagram_v4).
- spec: generate a diagram from a JSON/YAML architecture spec.
- compare: generate current/future diagrams from specs and write a diff summary.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from diagrams import Cluster, Diagram, Edge
    from diagrams.generic.blank import Blank
    DIAGRAMS_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependent
    Cluster = Diagram = Edge = Blank = None
    DIAGRAMS_IMPORT_ERROR = exc

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


ICON_ALIASES = {
    "aws.alb": "diagrams.aws.network.ALB",
    "aws.elb": "diagrams.aws.network.ELB",
    "aws.vpc": "diagrams.aws.network.VPC",
    "aws.subnet.private": "diagrams.aws.network.PrivateSubnet",
    "aws.subnet.public": "diagrams.aws.network.PublicSubnet",
    "aws.tgw": "diagrams.aws.network.TransitGateway",
    "aws.directconnect": "diagrams.aws.network.DirectConnect",
    "aws.nacl": "diagrams.aws.network.Nacl",
    "aws.nat": "diagrams.aws.network.NATGateway",
    "aws.igw": "diagrams.aws.network.InternetGateway",
    "aws.route53": "diagrams.aws.network.Route53",
    "aws.cloudfront": "diagrams.aws.network.CloudFront",
    "aws.endpoint": "diagrams.aws.network.Endpoint",
    "aws.ec2": "diagrams.aws.compute.EC2",
    "aws.lambda": "diagrams.aws.compute.Lambda",
    "aws.ecs": "diagrams.aws.compute.ECS",
    "aws.eks": "diagrams.aws.compute.EKS",
    "aws.rds": "diagrams.aws.database.RDS",
    "aws.dynamodb": "diagrams.aws.database.Dynamodb",
    "aws.elasticache": "diagrams.aws.database.Elasticache",
    "aws.redshift": "diagrams.aws.database.Redshift",
    "aws.s3": "diagrams.aws.storage.S3",
    "aws.efs": "diagrams.aws.storage.EFS",
    "aws.ebs": "diagrams.aws.storage.EBS",
    "aws.sqs": "diagrams.aws.integration.SQS",
    "aws.sns": "diagrams.aws.integration.SNS",
    "aws.kinesis": "diagrams.aws.analytics.Kinesis",
    "aws.shield": "diagrams.aws.security.Shield",
    "aws.waf": "diagrams.aws.security.WAF",
    "generic.firewall": "diagrams.generic.network.Firewall",
    "generic.rack": "diagrams.generic.compute.Rack",
    "generic.blank": "diagrams.generic.blank.Blank",
    "onprem.user": "diagrams.onprem.client.User",
}

DEFAULT_GRAPH_ATTR = {
    "splines": "spline",
    "ranksep": "1.0",
    "nodesep": "0.75",
    "pad": "0.4",
}


def load_data_file(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise ValueError("YAML requested but PyYAML is not installed. Use JSON or install pyyaml.")
        data = yaml.safe_load(raw)
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            if yaml is None:
                raise
            data = yaml.safe_load(raw)

    if not isinstance(data, dict):
        raise ValueError("Spec must be a JSON/YAML object.")
    return data


def dotted_import(path: str):
    module_name, cls_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)


def resolve_icon(icon: Optional[str]):
    require_diagrams()
    if not icon:
        return Blank

    key = icon.strip().lower()
    resolved = ICON_ALIASES.get(key, icon)

    try:
        if "." not in resolved:
            return Blank
        return dotted_import(resolved)
    except Exception:
        return Blank


def require_diagrams() -> None:
    if DIAGRAMS_IMPORT_ERROR is not None:
        raise RuntimeError(
            "The 'diagrams' package is required to render diagrams. "
            f"Install it first (original import error: {DIAGRAMS_IMPORT_ERROR})."
        )


def normalize_state_spec(spec: Dict[str, Any], state: Optional[str] = None) -> Dict[str, Any]:
    if "states" in spec and isinstance(spec["states"], dict):
        states = spec["states"]
        if state:
            if state not in states:
                raise ValueError(f"State '{state}' not found. Available: {', '.join(states.keys())}")
            selected = states[state]
        else:
            if "current" in states:
                selected = states["current"]
            else:
                selected = next(iter(states.values()))
        if not isinstance(selected, dict):
            raise ValueError("State definition must be an object.")
        merged = {k: v for k, v in spec.items() if k != "states"}
        merged.update(selected)
        return merged

    if state:
        raise ValueError("State requested, but spec has no 'states' section.")
    return spec


def validate_spec(spec: Dict[str, Any]) -> None:
    for key in ("nodes", "edges", "clusters"):
        if key in spec and not isinstance(spec[key], list):
            raise ValueError(f"'{key}' must be a list.")

    node_ids = set()
    for node in spec.get("nodes", []):
        node_id = node.get("id")
        if not node_id:
            raise ValueError("Every node must include 'id'.")
        if node_id in node_ids:
            raise ValueError(f"Duplicate node id: '{node_id}'.")
        node_ids.add(node_id)

    cluster_ids = {c.get("id") for c in spec.get("clusters", [])}
    if None in cluster_ids:
        raise ValueError("Every cluster must include 'id'.")

    for node in spec.get("nodes", []):
        cluster = node.get("cluster")
        if cluster and cluster not in cluster_ids:
            raise ValueError(f"Node '{node['id']}' references unknown cluster '{cluster}'.")

    for edge in spec.get("edges", []):
        src = edge.get("from")
        dst = edge.get("to")
        if not src or not dst:
            raise ValueError("Every edge must include 'from' and 'to'.")
        if src not in node_ids or dst not in node_ids:
            raise ValueError(f"Edge '{src} -> {dst}' references unknown nodes.")


def build_cluster_children(clusters: List[Dict[str, Any]]) -> Dict[Optional[str], List[Dict[str, Any]]]:
    children: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
    by_id = {c["id"]: c for c in clusters}

    for c in clusters:
        parent = c.get("parent")
        if parent and parent not in by_id:
            raise ValueError(f"Cluster '{c['id']}' references unknown parent cluster '{parent}'.")
        children[parent].append(c)
    return children


def render_spec_diagram(spec: Dict[str, Any], output_file: str, output_format: str = "png") -> str:
    require_diagrams()
    validate_spec(spec)

    title = spec.get("title", "Architecture Diagram")
    direction = spec.get("direction", "TB")
    graph_attr = dict(DEFAULT_GRAPH_ATTR)
    graph_attr.update(spec.get("graph_attr", {}))
    node_attr = spec.get("node_attr")
    edge_attr = spec.get("edge_attr")

    nodes_by_cluster: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
    for node in spec.get("nodes", []):
        nodes_by_cluster[node.get("cluster")].append(node)

    cluster_children = build_cluster_children(spec.get("clusters", []))
    node_objs: Dict[str, Any] = {}

    def render_nodes_for_cluster(cluster_id: Optional[str]) -> None:
        for node in nodes_by_cluster.get(cluster_id, []):
            icon_class = resolve_icon(node.get("icon"))
            label = str(node.get("label") or node.get("name") or node["id"])
            node_objs[node["id"]] = icon_class(label)

    def render_cluster(cluster: Dict[str, Any]) -> None:
        c_label = str(cluster.get("label") or cluster["id"])
        c_graph_attr = cluster.get("graph_attr")
        with Cluster(c_label, graph_attr=c_graph_attr):
            render_nodes_for_cluster(cluster["id"])
            for child in cluster_children.get(cluster["id"], []):
                render_cluster(child)

    with Diagram(
        title,
        filename=output_file,
        show=False,
        outformat=output_format,
        direction=direction,
        graph_attr=graph_attr,
        node_attr=node_attr,
        edge_attr=edge_attr,
    ):
        render_nodes_for_cluster(None)
        for root_cluster in cluster_children.get(None, []):
            render_cluster(root_cluster)

        for edge in spec.get("edges", []):
            src = node_objs[edge["from"]]
            dst = node_objs[edge["to"]]

            edge_kwargs = {
                k: v
                for k, v in {
                    "label": edge.get("label"),
                    "color": edge.get("color"),
                    "style": edge.get("style"),
                    "penwidth": edge.get("penwidth"),
                    "dir": edge.get("dir"),
                }.items()
                if v is not None
            }
            edge_obj = Edge(**edge_kwargs)

            mode = str(edge.get("mode", "forward")).lower()
            if mode == "reverse":
                dst >> edge_obj >> src
            elif mode == "undirected":
                src - edge_obj - dst
            else:
                src >> edge_obj >> dst

    return f"{output_file}.{output_format}"


def run_aws_mode(args: argparse.Namespace) -> None:
    require_diagrams()
    import botocore.session
    import aws_to_diagram_v4 as aws

    target = aws.AwsImportTarget(args.profile, args.region)
    session = botocore.session.Session(profile=target.profile_name)

    account = aws.get_account(target, session)
    account_aliases = aws.get_account_aliases(target, session)
    if not account:
        raise RuntimeError("Could not get AWS account info. Verify profile and region.")

    print(f"Account: {account}")
    if account_aliases:
        print(f"Aliases: {', '.join(account_aliases)}")

    region_resources = aws.create_json(session, target)
    account_resources = aws.get_account_resources(session, target)

    data = {
        "accounts": [
            {
                "accountId": account,
                "accountAliases": account_aliases,
                "resources": account_resources,
                "regions": [{"regionId": target.region, "resources": region_resources}],
            }
        ]
    }

    if args.export_json:
        with open(args.export_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, cls=aws.DateTimeEncoder)
        print(f"AWS snapshot written to {args.export_json}")

    filtered = aws.filter_resources_by_tag(data, args.tag)
    aws.generate_diagram(filtered, args.output, args.tag, args.format, args.direction)


def normalize_edge(edge: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(edge.get("from", "")), str(edge.get("to", "")), str(edge.get("label", "")))


def compare_specs(current_spec: Dict[str, Any], future_spec: Dict[str, Any]) -> Dict[str, List[str]]:
    cur_nodes = {str(n["id"]) for n in current_spec.get("nodes", [])}
    fut_nodes = {str(n["id"]) for n in future_spec.get("nodes", [])}

    cur_edges = {normalize_edge(e) for e in current_spec.get("edges", [])}
    fut_edges = {normalize_edge(e) for e in future_spec.get("edges", [])}

    return {
        "nodes_added": sorted(fut_nodes - cur_nodes),
        "nodes_removed": sorted(cur_nodes - fut_nodes),
        "edges_added": sorted([" -> ".join((a, b)) + (f" ({l})" if l else "") for a, b, l in (fut_edges - cur_edges)]),
        "edges_removed": sorted([" -> ".join((a, b)) + (f" ({l})" if l else "") for a, b, l in (cur_edges - fut_edges)]),
    }


def write_compare_summary(summary: Dict[str, List[str]], path: Path) -> None:
    lines = ["# Architecture Diff", ""]
    for key, title in (
        ("nodes_added", "Nodes Added"),
        ("nodes_removed", "Nodes Removed"),
        ("edges_added", "Edges Added"),
        ("edges_removed", "Edges Removed"),
    ):
        lines.append(f"## {title}")
        items = summary[key]
        if not items:
            lines.append("- None")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_spec_mode(args: argparse.Namespace) -> None:
    spec = load_data_file(Path(args.spec))
    state_spec = normalize_state_spec(spec, state=args.state)
    output = render_spec_diagram(state_spec, args.output, output_format=args.format)
    print(f"Diagram generated: {output}")


def run_compare_mode(args: argparse.Namespace) -> None:
    if args.spec:
        root = load_data_file(Path(args.spec))
        if "states" not in root:
            raise ValueError("--spec compare mode requires a 'states' object with 'current' and 'future'.")
        current_spec = normalize_state_spec(root, "current")
        future_spec = normalize_state_spec(root, "future")
    else:
        if not args.current or not args.future:
            raise ValueError("Provide either --spec or both --current and --future.")
        current_spec = normalize_state_spec(load_data_file(Path(args.current)))
        future_spec = normalize_state_spec(load_data_file(Path(args.future)))

    current_output = f"{args.output_prefix}_current"
    future_output = f"{args.output_prefix}_future"

    print("Rendering current-state diagram...")
    current_file = render_spec_diagram(current_spec, current_output, output_format=args.format)
    print("Rendering future-state diagram...")
    future_file = render_spec_diagram(future_spec, future_output, output_format=args.format)

    summary = compare_specs(current_spec, future_spec)
    summary_md = Path(f"{args.output_prefix}_diff.md")
    summary_json = Path(f"{args.output_prefix}_diff.json")

    write_compare_summary(summary, summary_md)
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Current diagram: {current_file}")
    print(f"Future diagram: {future_file}")
    print(f"Diff summary: {summary_md}")
    print(f"Diff JSON: {summary_json}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate architecture diagrams for current/future states from AWS discovery "
            "or spec files (JSON/YAML)."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    aws_p = sub.add_parser("aws", help="Fetch AWS resources and render a diagram")
    aws_p.add_argument("--profile", "-p", required=True, help="AWS profile name")
    aws_p.add_argument("--region", "-r", required=True, help="AWS region")
    aws_p.add_argument("--tag", "-t", default="", help="Optional tag keyword filter")
    aws_p.add_argument("--output", "-o", default="aws_architecture", help="Output file prefix")
    aws_p.add_argument("--format", default="png", choices=["png", "pdf", "svg"], help="Output format")
    aws_p.add_argument("--direction", choices=["TB", "LR", "BT", "RL"], help="Diagram direction")
    aws_p.add_argument("--export-json", help="Optional path to save fetched AWS inventory JSON")
    aws_p.set_defaults(func=run_aws_mode)

    spec_p = sub.add_parser("spec", help="Render a diagram from a JSON/YAML spec")
    spec_p.add_argument("--spec", required=True, help="Path to spec file")
    spec_p.add_argument("--state", help="State name when spec contains a 'states' object")
    spec_p.add_argument("--output", "-o", default="architecture", help="Output file prefix")
    spec_p.add_argument("--format", default="png", choices=["png", "pdf", "svg"], help="Output format")
    spec_p.set_defaults(func=run_spec_mode)

    cmp_p = sub.add_parser("compare", help="Render current/future diagrams and produce a diff")
    cmp_p.add_argument("--spec", help="Single file containing states.current and states.future")
    cmp_p.add_argument("--current", help="Current-state spec file")
    cmp_p.add_argument("--future", help="Future-state spec file")
    cmp_p.add_argument("--output-prefix", "-o", default="architecture_compare", help="Output prefix")
    cmp_p.add_argument("--format", default="png", choices=["png", "pdf", "svg"], help="Output format")
    cmp_p.set_defaults(func=run_compare_mode)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
