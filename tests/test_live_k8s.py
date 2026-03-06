from __future__ import annotations

from unittest.mock import patch

from agent_diagrams.live_k8s import (
    _deployment_status,
    _externalsecret_status,
    _job_status,
    _pod_status,
    _pvc_status,
    annotate_spec,
    generate_namespace_spec,
    summarize_namespace,
)


# ── Status inference (pure functions) ──


def test_deployment_status_running():
    dep = {"spec": {"replicas": 3}, "status": {"readyReplicas": 3}}
    assert _deployment_status(dep) == "running"


def test_deployment_status_degraded():
    dep = {"spec": {"replicas": 3}, "status": {"readyReplicas": 1}}
    assert _deployment_status(dep) == "degraded"


def test_deployment_status_failed():
    dep = {"spec": {"replicas": 3}, "status": {"readyReplicas": 0}}
    assert _deployment_status(dep) == "failed"


def test_deployment_status_no_status():
    dep = {"spec": {"replicas": 2}, "status": {}}
    assert _deployment_status(dep) == "failed"


def test_pod_status_running():
    pod = {"status": {"phase": "Running", "containerStatuses": []}}
    assert _pod_status(pod) == "running"


def test_pod_status_crashloop():
    pod = {
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {"state": {"waiting": {"reason": "CrashLoopBackOff"}}}
            ],
        }
    }
    assert _pod_status(pod) == "crashloop"


def test_pod_status_oom():
    pod = {
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {"state": {"waiting": {"reason": "OOMKilled"}}}
            ],
        }
    }
    assert _pod_status(pod) == "failed"


def test_pod_status_succeeded():
    pod = {"status": {"phase": "Succeeded", "containerStatuses": []}}
    assert _pod_status(pod) == "healthy"


def test_pod_status_pending():
    pod = {"status": {"phase": "Pending"}}
    assert _pod_status(pod) == "pending"


def test_pod_status_unknown():
    pod = {"status": {"phase": "SomethingElse"}}
    assert _pod_status(pod) == "unknown"


def test_job_status_succeeded():
    job = {"status": {"succeeded": 1, "active": 0, "failed": 0}}
    assert _job_status(job) == "healthy"


def test_job_status_active():
    job = {"status": {"succeeded": 0, "active": 2, "failed": 0}}
    assert _job_status(job) == "running"


def test_job_status_failed():
    job = {"status": {"succeeded": 0, "active": 0, "failed": 3}}
    assert _job_status(job) == "failed"


def test_job_status_pending():
    job = {"status": {}}
    assert _job_status(job) == "pending"


def test_pvc_status_bound():
    pvc = {"status": {"phase": "Bound"}}
    assert _pvc_status(pvc) == "running"


def test_pvc_status_unbound():
    pvc = {"status": {"phase": "Pending"}}
    assert _pvc_status(pvc) == "failed"


def test_externalsecret_ready():
    es = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    assert _externalsecret_status(es) == "running"


def test_externalsecret_not_ready():
    es = {"status": {"conditions": [{"type": "Ready", "status": "False"}]}}
    assert _externalsecret_status(es) == "failed"


def test_externalsecret_no_conditions():
    es = {"status": {}}
    assert _externalsecret_status(es) == "unknown"


# ── generate_namespace_spec (mocked) ──


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_generate_namespace_spec_structure(mock_state, mock_k8s_namespace_state):
    mock_state.return_value = mock_k8s_namespace_state
    spec = generate_namespace_spec(namespace="default")
    assert "title" in spec
    assert "direction" in spec
    assert "clusters" in spec
    assert "nodes" in spec
    assert "edges" in spec
    assert spec["clusters"][0]["id"] == "ns"


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_generate_namespace_spec_deterministic(mock_state, mock_k8s_namespace_state):
    mock_state.return_value = mock_k8s_namespace_state
    s1 = generate_namespace_spec(namespace="default")
    mock_state.return_value = mock_k8s_namespace_state
    s2 = generate_namespace_spec(namespace="default")
    assert s1 == s2


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_generate_namespace_spec_edges(mock_state, mock_k8s_namespace_state):
    mock_state.return_value = mock_k8s_namespace_state
    spec = generate_namespace_spec(namespace="default")
    # api-svc selector matches api-server deployment labels
    edges_from_to = [(e["from"], e["to"]) for e in spec["edges"]]
    assert ("svc_api-svc", "deploy_api-server") in edges_from_to


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_generate_namespace_spec_node_status(mock_state, mock_k8s_namespace_state):
    mock_state.return_value = mock_k8s_namespace_state
    spec = generate_namespace_spec(namespace="default")
    deploy_node = next(n for n in spec["nodes"] if n["id"] == "deploy_api-server")
    assert deploy_node["status"] == "running"


# ── annotate_spec (mocked) ──


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_annotate_spec_sets_status(mock_state, mock_k8s_namespace_state):
    mock_state.return_value = mock_k8s_namespace_state
    spec = {
        "nodes": [
            {
                "id": "deploy_api-server",
                "label": "API Server",
                "k8s_resource": {"namespace": "default", "kind": "deployment", "name": "api-server"},
            }
        ],
        "edges": [],
    }
    result = annotate_spec(spec, namespaces=["default"])
    node = result["nodes"][0]
    assert node["status"] == "running"
    assert "[live: running]" in node["label"]


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_annotate_spec_no_namespaces(mock_state):
    spec = {
        "nodes": [{"id": "web", "label": "Web"}],
        "edges": [],
    }
    result = annotate_spec(spec, namespaces=None)
    # No k8s_resource, no namespaces -> returned unchanged
    assert result["nodes"][0]["label"] == "Web"
    assert "status" not in result["nodes"][0]


# ── summarize_namespace (mocked) ──


@patch("agent_diagrams.live_k8s.get_namespace_state")
def test_summarize_namespace(mock_state, mock_k8s_namespace_state):
    mock_state.return_value = mock_k8s_namespace_state
    result = summarize_namespace("default")
    assert result["namespace"] == "default"
    assert len(result["deployments"]) == 1
    assert result["deployments"][0]["name"] == "api-server"
    assert result["deployments"][0]["status"] == "running"
