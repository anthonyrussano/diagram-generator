from __future__ import annotations

from .model import Edge, GraphData, Node


def _edge_key(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.src, edge.dst, edge.rel, edge.source)


def dedupe_graph(graph: GraphData) -> GraphData:
    node_index: dict[str, Node] = {}
    for node in graph.nodes:
        if node.id not in node_index:
            node_index[node.id] = node
            continue

        # Merge sparse -> rich attrs when duplicate IDs are discovered.
        existing = node_index[node.id]
        existing.attrs = {**node.attrs, **existing.attrs}
        if len(node.label) > len(existing.label):
            existing.label = node.label

    edge_index: dict[tuple[str, str, str, str], Edge] = {}
    for edge in graph.edges:
        edge_index.setdefault(_edge_key(edge), edge)

    return GraphData(
        nodes=list(node_index.values()),
        edges=list(edge_index.values()),
        metadata=graph.metadata,
    )
