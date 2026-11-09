"""Deterministic, dependency-free Ferroprint project export for collected graphs.

Ferroprint's portable JSON schema is documented at:
https://github.com/anthonyrussano/ferroprint/blob/main/docs/LIVE.md

The source graph remains canonical: this exporter intentionally does not
include raw infrastructure attributes, metadata, secrets, or guessed cloud icons.
"""

from __future__ import annotations

import heapq
import json
from collections import defaultdict
from pathlib import Path

from agent_diagrams.model import GraphData, Node


_SHAPES = {
    "database": ("database", 120, 110),
    "db": ("database", 120, 110),
    "rds": ("database", 120, 110),
    "queue": ("queue", 200, 70),
    "sqs": ("queue", 200, 70),
    "actor": ("actor", 60, 90),
    "user": ("actor", 60, 90),
    "decision": ("decision", 160, 100),
    "service": ("service", 160, 80),
    "api": ("service", 160, 80),
    "deployment": ("service", 160, 80),
}
_DEFAULT_SHAPE = ("box", 160, 80)


def _shape_for(node: Node) -> tuple[str, int, int]:
    return _SHAPES.get(node.kind.lower(), _DEFAULT_SHAPE)


def _layers(graph: GraphData) -> dict[str, int]:
    """Kahn layers, then one non-invented fallback layer for remaining cycles."""
    ids = {n.id for n in graph.nodes}
    incoming = {node_id: 0 for node_id in ids}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        if edge.src not in ids or edge.dst not in ids:
            raise ValueError(
                f"Ferroprint export cannot represent missing endpoint: {edge.src!r} -> {edge.dst!r}"
            )
        if edge.src == edge.dst:
            raise ValueError(f"Ferroprint does not support self-loops: {edge.src!r}")
        if edge.dst not in outgoing[edge.src]:
            outgoing[edge.src].add(edge.dst)
            incoming[edge.dst] += 1

    ready = [node_id for node_id, degree in incoming.items() if degree == 0]
    heapq.heapify(ready)
    layers = {node_id: 0 for node_id in ready}
    while ready:
        current = heapq.heappop(ready)
        for following in sorted(outgoing[current]):
            layers[following] = max(layers.get(following, 0), layers[current] + 1)
            incoming[following] -= 1
            if incoming[following] == 0:
                heapq.heappush(ready, following)

    # Cyclic components cannot be topologically sorted. Keep all original
    # edges and place the remaining nodes without implying an acyclic order.
    remaining = sorted(ids - layers.keys())
    cycle_layer = max(layers.values(), default=-1) + 1
    for node_id in remaining:
        layers[node_id] = cycle_layer
    return layers


def render_ferroprint(
    graph: GraphData,
    output_path: Path,
    *,
    name: str = "Infrastructure diagram",
    direction: str = "LR",
) -> Path:
    """Write one editable Ferroprint JSON sheet with stable IDs and positions."""
    if direction not in {"LR", "RL", "TB", "BT"}:
        raise ValueError(f"Invalid Ferroprint direction: {direction}")
    ordered_nodes = sorted(graph.nodes, key=lambda node: node.id)
    if len({n.id for n in ordered_nodes}) != len(ordered_nodes):
        raise ValueError("Ferroprint export requires unique source node IDs")
    layers = _layers(graph)
    ordered_by_layer: dict[int, list[Node]] = defaultdict(list)
    for node in ordered_nodes:
        ordered_by_layer[layers[node.id]].append(node)

    max_layer = max(layers.values(), default=0)
    node_ids = {node.id: f"n{i + 1}" for i, node in enumerate(ordered_nodes)}
    nodes = []
    for layer in sorted(ordered_by_layer):
        for row, node in enumerate(ordered_by_layer[layer]):
            shape, width, height = _shape_for(node)
            axis = max_layer - layer if direction in {"RL", "BT"} else layer
            x, y = (80 + axis * 260, 80 + row * 160)
            if direction in {"TB", "BT"}:
                x, y = (80 + row * 260, 80 + axis * 160)
            nodes.append(
                {
                    "id": node_ids[node.id],
                    "type": shape,
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                    "label": node.label,
                    "sub": "",
                }
            )

    edges = []
    for index, edge in enumerate(
        sorted(graph.edges, key=lambda e: (e.src, e.dst, e.rel, e.source)), start=1
    ):
        edges.append(
            {
                "id": f"e{index}",
                "from": node_ids[edge.src],
                "to": node_ids[edge.dst],
                "label": edge.rel,
                "route": "elbow",
                "arrow": "end",
                "dashed": edge.attrs.get("dashed") is True,
            }
        )

    payload = {
        "meta": {"project": name, "drawnBy": "diagram-gen", "date": "", "rev": "A"},
        "settings": {"lettering": "technical", "caps": False, "grid": 20, "route": "elbow"},
        "active": "s1",
        "sheets": [
            {
                "id": "s1",
                "number": "A-101",
                "name": name[:24],
                "unit": "px",
                "nodes": nodes,
                "edges": edges,
            }
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path
