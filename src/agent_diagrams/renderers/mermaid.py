from __future__ import annotations

import re
from pathlib import Path

from agent_diagrams.model import GraphData


def _escape_label(text: str) -> str:
    return text.replace('"', "'").replace("\n", "<br/>")


def _escape_rel(text: str) -> str:
    return text.replace('"', "'").replace("\n", " ")


def _node_id(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]", "_", value)
    if normalized and normalized[0].isdigit():
        normalized = f"n_{normalized}"
    if not normalized:
        normalized = "node"
    return normalized


def _stable_node_id_map(graph: GraphData) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    ordered_ids: list[str] = [node.id for node in graph.nodes]
    for edge in graph.edges:
        ordered_ids.append(edge.src)
        ordered_ids.append(edge.dst)

    for raw_id in ordered_ids:
        if raw_id in mapping:
            continue
        base = _node_id(raw_id)
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        mapping[raw_id] = candidate
        used.add(candidate)
    return mapping


def render_mermaid(graph: GraphData, output_path: Path, direction: str = "LR") -> Path:
    lines: list[str] = [f"flowchart {direction}"]
    id_map = _stable_node_id_map(graph)

    for node in graph.nodes:
        lines.append(f'  {id_map[node.id]}["{_escape_label(node.label)}"]')

    for edge in graph.edges:
        src = id_map[edge.src]
        dst = id_map[edge.dst]
        rel = _escape_rel(edge.rel)
        lines.append(f"  {src} -->|{rel}| {dst}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")
    return output_path
