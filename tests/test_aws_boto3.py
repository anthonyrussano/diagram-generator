"""Tests for aws_boto3_mode.py pure functions and GraphData conversion.

Because aws_boto3_mode.py has top-level ``from diagrams import ...`` statements,
the module cannot be imported without the diagrams package + Graphviz. We inject
mock modules via sys.modules before importing.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Inject mock modules so aws_boto3_mode can be imported without Graphviz or boto3
_MOCK_MODULES = [
    "botocore",
    "botocore.session",
    "botocore.client",
    "diagrams",
    "diagrams.aws.compute",
    "diagrams.aws.database",
    "diagrams.aws.network",
    "diagrams.aws.storage",
    "diagrams.aws.integration",
    "diagrams.aws.analytics",
    "diagrams.aws.security",
    "diagrams.generic.blank",
]
_mocks = {}
for mod in _MOCK_MODULES:
    if mod not in sys.modules:
        _mocks[mod] = MagicMock()
        sys.modules[mod] = _mocks[mod]

from agent_diagrams.aws_boto3_mode import (  # noqa: E402
    ERRORS,
    boto3_to_graph_data,
    filter_resources_by_tag,
    format_label,
    get_resource_name,
    has_tag_keyword,
)


# ── has_tag_keyword ──


def test_has_tag_keyword_empty():
    assert has_tag_keyword({"Tags": [{"Key": "Name", "Value": "x"}]}, "") is True


def test_has_tag_keyword_match():
    resource = {"Tags": [{"Key": "env", "Value": "production"}]}
    assert has_tag_keyword(resource, "prod") is True


def test_has_tag_keyword_no_match():
    resource = {"Tags": [{"Key": "env", "Value": "staging"}]}
    assert has_tag_keyword(resource, "prod") is False


def test_has_tag_keyword_dict_tags():
    resource = {"Tags": {"Name": "my-server", "env": "prod"}}
    assert has_tag_keyword(resource, "prod") is True


# ── get_resource_name ──


def test_get_resource_name_from_name_tag():
    resource = {"Tags": [{"Key": "Name", "Value": "web-server"}], "InstanceId": "i-123"}
    assert get_resource_name(resource, "EC2") == "web-server"


def test_get_resource_name_fallback():
    resource = {"Tags": [], "InstanceId": "i-abc123"}
    assert get_resource_name(resource, "EC2") == "i-abc123"


def test_get_resource_name_no_tags():
    resource = {"FunctionName": "my-func"}
    assert get_resource_name(resource, "Lambda") == "my-func"


def test_get_resource_name_default():
    resource = {}
    result = get_resource_name(resource, "Unknown")
    assert result == "Unknown"


# ── format_label ──


def test_format_label_short():
    result = format_label("Short", max_width=20)
    assert result == "Short"


def test_format_label_wrapping():
    result = format_label("This is a very long label that should be wrapped", max_width=15)
    assert "\n" in result


def test_format_label_none():
    result = format_label(None)
    assert result == "Unknown"


# ── filter_resources_by_tag ──


def test_filter_empty_keyword():
    """Build the nested data structure that filter_resources_by_tag expects."""
    data = {
        "accounts": [{
            "accountId": "123",
            "accountAliases": [],
            "resources": {},
            "regions": [{
                "regionId": "us-east-1",
                "resources": {
                    "ec2": {
                        "instances": [
                            {"Instances": [{"InstanceId": "i-1", "Tags": [{"Key": "Name", "Value": "web"}]}]}
                        ],
                        "vpcs": [],
                        "subnets": [],
                        "routeTables": [],
                        "internetGateways": [],
                        "natGateways": [],
                        "vpcEndpoints": [],
                        "securityGroups": [],
                    },
                    "lambda": {"functions": []},
                    "rds": {"dbInstances": []},
                    "alb": {"loadBalancersV2": []},
                    "elb": {"loadBalancers": []},
                    "s3": {"buckets": []},
                    "dynamoDB": {"tables": []},
                },
            }],
        }]
    }
    result = filter_resources_by_tag(data, "")
    assert "ec2_instances" in result
    assert len(result["ec2_instances"]) == 1


# ── boto3_to_graph_data ──


def test_boto3_to_graph_data_basic(mock_aws_boto3_filtered):
    graph = boto3_to_graph_data(mock_aws_boto3_filtered, "default", "us-east-1")
    node_ids = {n.id for n in graph.nodes}
    assert "aws:vpc:vpc-111" in node_ids
    assert "aws:subnet:subnet-aaa" in node_ids
    assert "aws:ec2:i-abc123" in node_ids
    assert "aws:s3:my-bucket" in node_ids
    assert graph.metadata["source"] == "aws-boto3"


def test_boto3_to_graph_data_edges(mock_aws_boto3_filtered):
    graph = boto3_to_graph_data(mock_aws_boto3_filtered, "default", "us-east-1")
    edge_pairs = {(e.src, e.dst, e.rel) for e in graph.edges}
    assert ("aws:subnet:subnet-aaa", "aws:vpc:vpc-111", "in") in edge_pairs
    assert ("aws:ec2:i-abc123", "aws:subnet:subnet-aaa", "in") in edge_pairs


def test_boto3_to_graph_data_lambda_vpc():
    resources = {
        "lambda_functions": [
            {
                "FunctionArn": "arn:aws:lambda:us-east-1:123:function:f1",
                "FunctionName": "f1",
                "VpcConfig": {"SubnetIds": ["subnet-x"]},
            }
        ],
        "ec2_instances": [], "rds_instances": [], "albs": [], "s3_buckets": [],
        "dynamodb_tables": [], "vpcs": [], "subnets": [], "sqs_queues": [],
        "sns_topics": [], "ecs_clusters": [], "eks_clusters": [],
    }
    graph = boto3_to_graph_data(resources, "p", "r")
    edges = [(e.src, e.rel) for e in graph.edges]
    assert any("lambda" in src and rel == "runs_in" for src, rel in edges)


def test_boto3_to_graph_data_empty():
    resources = {
        "ec2_instances": [], "lambda_functions": [], "rds_instances": [],
        "albs": [], "s3_buckets": [], "dynamodb_tables": [], "vpcs": [],
        "subnets": [], "sqs_queues": [], "sns_topics": [],
        "ecs_clusters": [], "eks_clusters": [],
    }
    graph = boto3_to_graph_data(resources, "p", "r")
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0
