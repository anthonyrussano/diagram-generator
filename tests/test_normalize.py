from agent_diagrams.model import Node, Edge, GraphData
from agent_diagrams.normalize import dedupe_graph


def test_dedupe_removes_duplicate_nodes(duplicate_graph):
    result = dedupe_graph(duplicate_graph)
    assert len(result.nodes) == 2
    ids = {n.id for n in result.nodes}
    assert ids == {"n1", "n2"}


def test_dedupe_keeps_longer_label(duplicate_graph):
    result = dedupe_graph(duplicate_graph)
    n1 = next(n for n in result.nodes if n.id == "n1")
    assert n1.label == "LongerLabel"


def test_dedupe_merges_attrs(duplicate_graph):
    result = dedupe_graph(duplicate_graph)
    n1 = next(n for n in result.nodes if n.id == "n1")
    # existing attrs take precedence; new attrs ("extra") fill in
    assert n1.attrs.get("extra") is True


def test_dedupe_removes_duplicate_edges(duplicate_graph):
    result = dedupe_graph(duplicate_graph)
    assert len(result.edges) == 1


def test_dedupe_preserves_unique_edges():
    g = GraphData()
    g.add_node(Node(id="a", label="A", kind="k", source="s"))
    g.add_node(Node(id="b", label="B", kind="k", source="s"))
    g.add_edge(Edge(src="a", dst="b", rel="r1", source="s"))
    g.add_edge(Edge(src="a", dst="b", rel="r2", source="s"))
    result = dedupe_graph(g)
    assert len(result.edges) == 2


def test_dedupe_deterministic_order():
    g = GraphData()
    for i in range(10):
        g.add_node(Node(id=f"n{i}", label=f"N{i}", kind="k", source="s"))
        if i > 0:
            g.add_edge(Edge(src=f"n{i}", dst=f"n{i-1}", rel="r", source="s"))

    first = dedupe_graph(g)
    for _ in range(50):
        result = dedupe_graph(g)
        assert [n.id for n in result.nodes] == [n.id for n in first.nodes]
        assert [(e.src, e.dst) for e in result.edges] == [(e.src, e.dst) for e in first.edges]


def test_dedupe_empty_graph():
    g = GraphData()
    result = dedupe_graph(g)
    assert result.nodes == []
    assert result.edges == []


def test_dedupe_preserves_metadata():
    g = GraphData(metadata={"source": "test", "extra": 42})
    result = dedupe_graph(g)
    assert result.metadata == {"source": "test", "extra": 42}
