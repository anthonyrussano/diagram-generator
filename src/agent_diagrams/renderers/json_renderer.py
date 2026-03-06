from __future__ import annotations

import json
from pathlib import Path

from agent_diagrams.model import GraphData


def render_json(graph: GraphData, output_path: Path) -> Path:
    payload = {
        "metadata": graph.metadata,
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "kind": n.kind,
                "source": n.source,
                "attrs": n.attrs,
            }
            for n in graph.nodes
        ],
        "edges": [
            {
                "src": e.src,
                "dst": e.dst,
                "rel": e.rel,
                "source": e.source,
                "attrs": e.attrs,
            }
            for e in graph.edges
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    return output_path
