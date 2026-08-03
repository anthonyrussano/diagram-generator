from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from agent_diagrams.collectors import (
    collect_from_aws_cli,
    collect_from_json,
    collect_from_kubernetes,
    collect_from_terraform,
    discover_files,
)


# ── AWS CLI collector ──


def _make_aws_responses():
    """Return side_effect list for the 10 _run_json calls in collect_from_aws_cli."""
    return [
        {"Vpcs": [{"VpcId": "vpc-1"}]},
        {"Subnets": [{"SubnetId": "subnet-1", "VpcId": "vpc-1"}]},
        {"Reservations": [{"Instances": [{"InstanceId": "i-1", "SubnetId": "subnet-1"}]}]},
        {"Functions": [{"FunctionArn": "arn:aws:lambda:us-east-1:123:function:f1", "FunctionName": "f1"}]},
        {"DBInstances": [{"DBInstanceIdentifier": "db-1"}]},
        {"LoadBalancers": []},
        {"Buckets": [{"Name": "my-bucket"}]},
        {"TableNames": ["t1"]},
        {"clusters": []},
        {"clusterArns": []},
    ]


@patch("agent_diagrams.collectors._run_json")
def test_collect_from_aws_cli_basic(mock_run_json):
    mock_run_json.side_effect = _make_aws_responses()
    g = collect_from_aws_cli(profile="test", region="us-east-1")

    assert g.metadata["source"] == "aws"
    assert len(g.nodes) >= 5  # vpc + subnet + ec2 + lambda + rds + s3 + dynamodb
    node_ids = {n.id for n in g.nodes}
    assert "aws:vpc:vpc-1" in node_ids
    assert "aws:ec2:i-1" in node_ids
    assert "aws:s3:my-bucket" in node_ids

    # Edges: subnet->vpc, ec2->subnet
    edge_pairs = {(e.src, e.dst) for e in g.edges}
    assert ("aws:subnet:subnet-1", "aws:vpc:vpc-1") in edge_pairs
    assert ("aws:ec2:i-1", "aws:subnet:subnet-1") in edge_pairs


@patch("agent_diagrams.collectors._run_json")
def test_collect_from_aws_cli_empty(mock_run_json):
    mock_run_json.return_value = {}
    g = collect_from_aws_cli(profile="test", region="us-east-1")
    assert len(g.nodes) == 0
    assert len(g.edges) == 0


# ── JSON collector ──


def test_collect_from_json_graph_format(tmp_path):
    data = {
        "nodes": [
            {"id": "n1", "label": "Node 1", "kind": "custom"},
            {"id": "n2", "label": "Node 2"},
        ],
        "edges": [{"src": "n1", "dst": "n2", "rel": "connects"}],
    }
    f = tmp_path / "test.json"
    f.write_text(json.dumps(data))

    g = collect_from_json([f])
    assert len(g.nodes) == 2
    assert len(g.edges) == 1
    assert g.nodes[0].kind == "custom"
    assert g.nodes[1].kind == "json.node"
    assert g.edges[0].rel == "connects"


def test_collect_from_json_uses_repo_relative_metadata_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    graph_file = inputs / "graph.json"
    graph_file.write_text(json.dumps({"nodes": [{"id": "n1"}]}))

    graph = collect_from_json([graph_file.resolve()])

    assert graph.metadata["inputs"] == ["inputs/graph.json"]


def test_collect_from_json_opaque_file(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"setting": "value"}))

    g = collect_from_json([f])
    assert len(g.nodes) == 1
    assert g.nodes[0].kind == "json.file"
    assert g.nodes[0].id == "json:file:config.json"


# ── Terraform collector ──


def test_collect_from_terraform_state(tmp_path):
    data = {
        "resources": [
            {"type": "aws_instance", "name": "web"},
            {"type": "aws_s3_bucket", "name": "data"},
        ]
    }
    f = tmp_path / "main.tfstate"
    f.write_text(json.dumps(data))

    g = collect_from_terraform([f])
    assert len(g.nodes) == 2
    assert {n.id for n in g.nodes} == {"tf:aws_instance.web", "tf:aws_s3_bucket.data"}


def test_collect_from_terraform_config_with_depends_on(tmp_path):
    data = {
        "resource": {
            "aws_instance": {
                "web": {"ami": "ami-123", "depends_on": ["aws_vpc.main"]}
            },
            "aws_vpc": {"main": {"cidr_block": "10.0.0.0/16"}},
        }
    }
    f = tmp_path / "infra.tf.json"
    f.write_text(json.dumps(data))

    g = collect_from_terraform([f])
    assert len(g.nodes) == 2
    assert len(g.edges) == 1
    assert g.edges[0].rel == "depends_on"
    assert g.edges[0].dst == "tf:aws_vpc.main"


# ── Kubernetes collector ──


def test_collect_from_kubernetes_manifests(tmp_path):
    docs = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "prod"},
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "api-svc",
                "namespace": "prod",
                "ownerReferences": [{"kind": "Deployment", "name": "api"}],
            },
        },
    ]

    f = tmp_path / "k8s-manifests.yaml"
    with f.open("w") as fh:
        yaml.dump_all(docs, fh)

    g = collect_from_kubernetes([f], use_live_cluster=False)
    assert len(g.nodes) == 2
    assert len(g.edges) == 1
    assert g.edges[0].rel == "owned_by"
    assert g.edges[0].dst == "k8s:prod:Deployment:api"


def test_collect_from_kubernetes_extra_docs(tmp_path):
    extra = [
        {"kind": "ConfigMap", "metadata": {"name": "cm-1", "namespace": "default"}}
    ]
    g = collect_from_kubernetes([], use_live_cluster=False, extra_docs=extra)
    assert len(g.nodes) == 1
    assert g.nodes[0].id == "k8s:default:ConfigMap:cm-1"


# ── discover_files ──


def test_discover_files(tmp_path):
    (tmp_path / "data.json").touch()
    (tmp_path / "state.tfstate").touch()
    (tmp_path / "infra.tf.json").touch()
    (tmp_path / "k8s-deploy.yaml").touch()
    (tmp_path / "irrelevant.txt").touch()

    found = discover_files(tmp_path)
    # infra.tf.json matches both *.json and *.tf.json globs
    assert len(found["json"]) == 2
    assert len(found["tfstate"]) == 1
    assert len(found["tfjson"]) == 1
    assert len(found["k8s"]) == 1
