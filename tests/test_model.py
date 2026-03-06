from agent_diagrams.model import Node, Edge, GraphData


def test_node_creation():
    n = Node(id="n1", label="Node 1", kind="aws.ec2", source="test")
    assert n.id == "n1"
    assert n.label == "Node 1"
    assert n.kind == "aws.ec2"
    assert n.source == "test"
    assert n.attrs == {}


def test_node_attrs_default_independent():
    n1 = Node(id="a", label="A", kind="x", source="s")
    n2 = Node(id="b", label="B", kind="x", source="s")
    n1.attrs["key"] = "value"
    assert "key" not in n2.attrs


def test_edge_creation():
    e = Edge(src="a", dst="b", rel="in", source="test")
    assert e.src == "a"
    assert e.dst == "b"
    assert e.rel == "in"
    assert e.attrs == {}


def test_graph_data_defaults():
    g = GraphData()
    assert g.nodes == []
    assert g.edges == []
    assert g.metadata == {}


def test_graph_data_add_node():
    g = GraphData()
    n = Node(id="n1", label="N", kind="k", source="s")
    g.add_node(n)
    assert len(g.nodes) == 1
    assert g.nodes[0] is n


def test_graph_data_add_edge():
    g = GraphData()
    e = Edge(src="a", dst="b", rel="r", source="s")
    g.add_edge(e)
    assert len(g.edges) == 1
    assert g.edges[0] is e


def test_graph_data_metadata():
    g = GraphData(metadata={"source": "aws", "region": "us-east-1"})
    assert g.metadata["source"] == "aws"
    assert g.metadata["region"] == "us-east-1"
