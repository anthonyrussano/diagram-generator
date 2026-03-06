from __future__ import annotations

import pytest
from pathlib import Path

from agent_diagrams.model import Node, Edge, GraphData

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture
def simple_graph() -> GraphData:
    """Minimal graph with 3 nodes and 2 edges — deterministic IDs."""
    g = GraphData(metadata={"source": "test"})
    g.add_node(Node(id="vpc-1", label="VPC One", kind="aws.vpc", source="test"))
    g.add_node(Node(id="subnet-1", label="Subnet One", kind="aws.subnet", source="test"))
    g.add_node(Node(id="ec2-1", label="Instance One", kind="aws.ec2", source="test"))
    g.add_edge(Edge(src="subnet-1", dst="vpc-1", rel="in", source="test"))
    g.add_edge(Edge(src="ec2-1", dst="subnet-1", rel="in", source="test"))
    return g


@pytest.fixture
def duplicate_graph() -> GraphData:
    """Graph with intentional duplicates for dedup testing."""
    g = GraphData(metadata={"source": "test"})
    g.add_node(Node(id="n1", label="Short", kind="a", source="s1"))
    g.add_node(Node(id="n1", label="LongerLabel", kind="a", source="s1", attrs={"extra": True}))
    g.add_node(Node(id="n2", label="Two", kind="b", source="s2"))
    g.add_edge(Edge(src="n1", dst="n2", rel="r", source="s1"))
    g.add_edge(Edge(src="n1", dst="n2", rel="r", source="s1"))
    return g


@pytest.fixture
def sample_spec() -> dict:
    """Minimal spec dict for spec_workflows tests."""
    return {
        "title": "Test Architecture",
        "direction": "TB",
        "nodes": [
            {"id": "web", "label": "Web Server", "icon": "aws.ec2"},
            {"id": "db", "label": "Database", "icon": "aws.rds"},
        ],
        "edges": [
            {"from": "web", "to": "db", "label": "SQL"},
        ],
        "clusters": [],
    }


@pytest.fixture
def multi_state_spec() -> dict:
    """Spec with states.current and states.future for compare tests."""
    return {
        "title": "Migration",
        "states": {
            "current": {
                "nodes": [
                    {"id": "web", "label": "Web Server", "icon": "aws.ec2"},
                    {"id": "db", "label": "Old DB", "icon": "aws.rds"},
                ],
                "edges": [{"from": "web", "to": "db", "label": "SQL"}],
                "clusters": [],
            },
            "future": {
                "nodes": [
                    {"id": "web", "label": "Web Server", "icon": "aws.ec2"},
                    {"id": "db", "label": "Old DB", "icon": "aws.rds"},
                    {"id": "cache", "label": "Redis Cache", "icon": "aws.elasticache"},
                ],
                "edges": [
                    {"from": "web", "to": "cache", "label": "get/set"},
                    {"from": "cache", "to": "db", "label": "SQL"},
                ],
                "clusters": [],
            },
        },
    }


@pytest.fixture
def mock_k8s_namespace_state() -> dict:
    """Mocked return value from get_namespace_state for live_k8s tests."""
    return {
        "deployments": [
            {
                "metadata": {"name": "api-server", "namespace": "default"},
                "spec": {
                    "replicas": 3,
                    "template": {
                        "metadata": {"labels": {"app": "api"}},
                        "spec": {"containers": [{"image": "api:v1.2.3", "name": "api"}]},
                    },
                },
                "status": {"readyReplicas": 3},
            }
        ],
        "pods": [],
        "services": [
            {
                "metadata": {"name": "api-svc", "namespace": "default"},
                "spec": {
                    "selector": {"app": "api"},
                    "ports": [{"port": 80, "protocol": "TCP"}],
                },
            }
        ],
        "ingresses": [],
        "jobs": [],
        "persistentvolumeclaims": [],
        "externalsecrets": [],
    }


@pytest.fixture
def mock_aws_boto3_filtered() -> dict:
    """Minimal filtered_resources dict for aws_boto3 tests."""
    return {
        "ec2_instances": [
            {
                "InstanceId": "i-abc123",
                "InstanceType": "t3.medium",
                "State": {"Name": "running"},
                "VpcId": "vpc-111",
                "SubnetId": "subnet-aaa",
                "Tags": [{"Key": "Name", "Value": "webserver"}],
                "SecurityGroups": [],
                "PrivateIpAddress": "10.0.1.10",
            }
        ],
        "lambda_functions": [],
        "rds_instances": [],
        "albs": [],
        "elbs": [],
        "s3_buckets": [{"Name": "my-bucket", "Tags": []}],
        "dynamodb_tables": [],
        "vpcs": [{"VpcId": "vpc-111", "CidrBlock": "10.0.0.0/16", "Tags": []}],
        "subnets": [
            {
                "SubnetId": "subnet-aaa",
                "VpcId": "vpc-111",
                "CidrBlock": "10.0.1.0/24",
                "AvailabilityZone": "us-east-1a",
                "MapPublicIpOnLaunch": False,
                "Tags": [],
            }
        ],
        "security_groups": [],
        "ecs_clusters": [],
        "eks_clusters": [],
        "sqs_queues": [],
        "sns_topics": [],
        "route53_zones": [],
        "ebs_volumes": [],
        "target_groups": [],
        "route_tables": [],
        "internet_gateways": [],
        "nat_gateways": [],
        "vpc_endpoints": [],
        "vpc_peerings": [],
        "availability_zones": [],
    }
