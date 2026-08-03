from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .icon_catalog import resolve_spec_icon
from .renderers.diagrams_renderer import _inline_svg_image_refs, load_icon_factory

try:
    from diagrams import Cluster, Diagram, Edge
    from diagrams.generic.blank import Blank

    DIAGRAMS_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependent
    Cluster = Diagram = Edge = Blank = None
    DIAGRAMS_IMPORT_ERROR = exc


DEFAULT_GRAPH_ATTR = {
    "splines": "spline",
    "ranksep": "1.0",
    "nodesep": "0.75",
    "pad": "0.4",
    "labelloc": "t",
    "labeljust": "c",
    "fontname": "Sans-Serif",
    "fontsize": "13",
}

DEFAULT_NODE_ATTR = {
    "fontname": "Sans-Serif",
    "fontsize": "11",
}

DEFAULT_EDGE_ATTR = {
    "fontname": "Sans-Serif",
    "fontsize": "10",
}

STATUS_STYLES: dict[str, dict[str, str]] = {
    "running": {"fontcolor": "#1a7f37", "color": "#1a7f37"},
    "healthy": {"fontcolor": "#1a7f37", "color": "#1a7f37"},
    "degraded": {"fontcolor": "#b45309", "color": "#b45309"},
    "failed": {"fontcolor": "#b91c1c", "color": "#b91c1c"},
    "crashloop": {"fontcolor": "#b91c1c", "color": "#b91c1c"},
    "error": {"fontcolor": "#b91c1c", "color": "#b91c1c"},
    "pending": {"fontcolor": "#6b7280", "color": "#6b7280"},
    "unknown": {"fontcolor": "#6b7280", "color": "#6b7280"},
}


def require_diagrams() -> None:
    if DIAGRAMS_IMPORT_ERROR is not None:
        raise RuntimeError(
            "The 'diagrams' package is required to render spec diagrams. "
            f"Install it first (original import error: {DIAGRAMS_IMPORT_ERROR})."
        )


def load_data_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = yaml.safe_load(raw)

    if not isinstance(data, dict):
        raise ValueError("Spec must be a JSON/YAML object.")
    return data


def normalize_state_spec(spec: dict[str, Any], state: str | None = None) -> dict[str, Any]:
    if "states" in spec and isinstance(spec["states"], dict):
        states = spec["states"]
        if state:
            if state not in states:
                raise ValueError(f"State '{state}' not found. Available: {', '.join(states.keys())}")
            selected = states[state]
        elif "current" in states:
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


def _validate_mapping(value: Any, location: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"'{location}' must be an object.")


def _validate_collection(spec: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = spec.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"'{key}' must be a list.")
    for index, item in enumerate(value):
        _validate_mapping(item, f"{key}[{index}]")
    return value


def _validate_cluster_hierarchy(clusters: list[dict[str, Any]]) -> None:
    cluster_by_id = {cluster["id"]: cluster for cluster in clusters}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(cluster_id: str) -> None:
        if cluster_id in visited:
            return
        if cluster_id in visiting:
            raise ValueError(f"Cluster hierarchy contains a cycle at '{cluster_id}'.")

        visiting.add(cluster_id)
        parent = cluster_by_id[cluster_id].get("parent")
        if parent:
            if parent not in cluster_by_id:
                raise ValueError(f"Cluster '{cluster_id}' references unknown parent cluster '{parent}'.")
            visit(parent)
        visiting.remove(cluster_id)
        visited.add(cluster_id)

    for cluster_id in cluster_by_id:
        visit(cluster_id)


def validate_spec(spec: dict[str, Any]) -> None:
    nodes = _validate_collection(spec, "nodes")
    edges = _validate_collection(spec, "edges")
    clusters = _validate_collection(spec, "clusters")

    direction = spec.get("direction")
    if direction is not None and direction not in {"TB", "LR", "BT", "RL"}:
        raise ValueError("'direction' must be one of: TB, LR, BT, RL.")

    for key in ("graph_attr", "node_attr", "edge_attr"):
        if key in spec:
            _validate_mapping(spec[key], key)

    node_ids: set[str] = set()
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("Every node must include 'id'.")
        if node_id in node_ids:
            raise ValueError(f"Duplicate node id: '{node_id}'.")
        node_ids.add(node_id)
        if "attrs" in node:
            _validate_mapping(node["attrs"], f"node '{node_id}' attrs")

    cluster_ids: set[str] = set()
    for cluster in clusters:
        cluster_id = cluster.get("id")
        if not isinstance(cluster_id, str) or not cluster_id.strip():
            raise ValueError("Every cluster must include 'id'.")
        if cluster_id in cluster_ids:
            raise ValueError(f"Duplicate cluster id: '{cluster_id}'.")
        cluster_ids.add(cluster_id)
        parent = cluster.get("parent")
        if parent is not None and (not isinstance(parent, str) or not parent.strip()):
            raise ValueError(f"Cluster '{cluster_id}' parent must be a non-empty string.")
        if "graph_attr" in cluster:
            _validate_mapping(cluster["graph_attr"], f"cluster '{cluster_id}' graph_attr")

    _validate_cluster_hierarchy(clusters)

    for node in nodes:
        cluster = node.get("cluster")
        if cluster is not None and (not isinstance(cluster, str) or not cluster.strip()):
            raise ValueError(f"Node '{node['id']}' cluster must be a non-empty string.")
        if cluster and cluster not in cluster_ids:
            raise ValueError(f"Node '{node['id']}' references unknown cluster '{cluster}'.")

    for edge in edges:
        src = edge.get("from")
        dst = edge.get("to")
        if not isinstance(src, str) or not src.strip() or not isinstance(dst, str) or not dst.strip():
            raise ValueError("Every edge must include 'from' and 'to'.")
        if src not in node_ids or dst not in node_ids:
            raise ValueError(f"Edge '{src} -> {dst}' references unknown nodes.")
        mode = str(edge.get("mode", "forward")).lower()
        if mode not in {"forward", "reverse", "undirected"}:
            raise ValueError(
                f"Edge '{src} -> {dst}' has invalid mode '{mode}'. "
                "Use forward, reverse, or undirected."
            )
        if "attrs" in edge:
            _validate_mapping(edge["attrs"], f"edge '{src} -> {dst}' attrs")


def spec_counts(spec: dict[str, Any]) -> dict[str, int]:
    return {
        "nodes": len(spec.get("nodes", [])),
        "edges": len(spec.get("edges", [])),
        "clusters": len(spec.get("clusters", [])),
    }


def edge_attributes(edge: dict[str, Any]) -> dict[str, Any]:
    attrs = dict(edge.get("attrs") or {})
    for key in ("label", "color", "style", "penwidth", "dir"):
        value = edge.get(key)
        if value is not None:
            attrs[key] = value
    return attrs


def _resolve_icon(icon: str | None):
    require_diagrams()
    return load_icon_factory(resolve_spec_icon(icon))


def _build_cluster_children(clusters: list[dict[str, Any]]) -> dict[str | None, list[dict[str, Any]]]:
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    by_id = {c["id"]: c for c in clusters}

    for cluster in clusters:
        parent = cluster.get("parent")
        if parent and parent not in by_id:
            raise ValueError(f"Cluster '{cluster['id']}' references unknown parent cluster '{parent}'.")
        children[parent].append(cluster)
    return children


def render_spec_diagram(
    spec: dict[str, Any],
    output_prefix: Path,
    *,
    output_format: str = "png",
    direction: str | None = None,
) -> Path:
    require_diagrams()
    validate_spec(spec)

    title = str(spec.get("title") or "Architecture Diagram")
    render_direction = direction or str(spec.get("direction") or "TB")

    graph_attr = dict(DEFAULT_GRAPH_ATTR)
    graph_attr.update(spec.get("graph_attr") or {})

    node_attr = dict(DEFAULT_NODE_ATTR)
    node_attr.update(spec.get("node_attr") or {})

    edge_attr = dict(DEFAULT_EDGE_ATTR)
    edge_attr.update(spec.get("edge_attr") or {})

    nodes_by_cluster: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for node in spec.get("nodes", []):
        nodes_by_cluster[node.get("cluster")].append(node)

    cluster_children = _build_cluster_children(spec.get("clusters", []))
    node_objs: dict[str, Any] = {}

    def render_nodes_for_cluster(cluster_id: str | None) -> None:
        for node in nodes_by_cluster.get(cluster_id, []):
            icon_class = _resolve_icon(node.get("icon"))
            label = str(node.get("label") or node.get("name") or node["id"])

            node_kwargs: dict[str, str] = {}
            status = str(node.get("status", "")).lower()
            if status in STATUS_STYLES:
                node_kwargs.update(STATUS_STYLES[status])
            node_kwargs.update(node.get("attrs") or {})

            node_objs[node["id"]] = icon_class(label, **node_kwargs)

    def render_cluster(cluster: dict[str, Any]) -> None:
        label = str(cluster.get("label") or cluster["id"])
        with Cluster(label, graph_attr=cluster.get("graph_attr")):
            render_nodes_for_cluster(cluster["id"])
            for child in cluster_children.get(cluster["id"], []):
                render_cluster(child)

    output_prefix = output_prefix.resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    with Diagram(
        title,
        filename=str(output_prefix),
        show=False,
        outformat=output_format,
        direction=render_direction,
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
            edge_obj = Edge(**edge_attributes(edge))

            mode = str(edge.get("mode", "forward")).lower()
            if mode == "reverse":
                dst >> edge_obj >> src
            elif mode == "undirected":
                src - edge_obj - dst
            else:
                src >> edge_obj >> dst

    output_path = output_prefix.parent / f"{output_prefix.name}.{output_format}"
    if output_format == "svg":
        _inline_svg_image_refs(output_path)
    return output_path


def _normalize_edge(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(edge.get("from", "")),
        str(edge.get("to", "")),
        str(edge.get("label", "")),
    )


def compare_specs(current_spec: dict[str, Any], future_spec: dict[str, Any]) -> dict[str, list[str]]:
    cur_nodes = {str(node["id"]) for node in current_spec.get("nodes", [])}
    fut_nodes = {str(node["id"]) for node in future_spec.get("nodes", [])}

    cur_edges = {_normalize_edge(edge) for edge in current_spec.get("edges", [])}
    fut_edges = {_normalize_edge(edge) for edge in future_spec.get("edges", [])}

    return {
        "nodes_added": sorted(fut_nodes - cur_nodes),
        "nodes_removed": sorted(cur_nodes - fut_nodes),
        "edges_added": sorted(
            [
                " -> ".join((src, dst)) + (f" ({label})" if label else "")
                for src, dst, label in (fut_edges - cur_edges)
            ]
        ),
        "edges_removed": sorted(
            [
                " -> ".join((src, dst)) + (f" ({label})" if label else "")
                for src, dst, label in (cur_edges - fut_edges)
            ]
        ),
    }


def write_compare_summary(summary: dict[str, list[str]], path: Path) -> None:
    lines = ["# Architecture Diff", ""]
    for key, title in (
        ("nodes_added", "Nodes Added"),
        ("nodes_removed", "Nodes Removed"),
        ("edges_added", "Edges Added"),
        ("edges_removed", "Edges Removed"),
    ):
        lines.append(f"## {title}")
        entries = summary[key]
        if not entries:
            lines.append("- None")
        else:
            for entry in entries:
                lines.append(f"- {entry}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
