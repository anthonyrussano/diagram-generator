from __future__ import annotations

from agent_diagrams.collectors import collect_from_kubernetes


def obj(kind, name, namespace="prod", **fields):
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "namespace": namespace},
        **fields,
    }


def collect(docs):
    return collect_from_kubernetes([], False, docs)


def relationships(graph):
    return {(edge.src, edge.dst, edge.rel) for edge in graph.edges}


def test_services_match_template_labels_and_respect_namespaces():
    deployment = obj(
        "Deployment",
        "web",
        spec={"template": {"metadata": {"labels": {"app": "web"}}, "spec": {}}},
    )
    wrong_namespace = obj("Pod", "other", "dev", spec={})
    wrong_namespace["metadata"]["labels"] = {"app": "web"}
    graph = collect(
        [
            deployment,
            wrong_namespace,
            obj("Service", "web", spec={"selector": {"app": "web"}}),
        ]
    )
    assert relationships(graph) == {
        ("k8s:prod:Service:web", "k8s:prod:Deployment:web", "selects")
    }
    assert graph.edges[0].attrs["matched_on"] == "pod_template_labels"


def test_pod_selectors_prefer_observed_pods_and_match_expressions():
    pod = obj("Pod", "web", spec={})
    pod["metadata"]["labels"] = {"app": "web", "tier": "backend"}
    deployment = obj(
        "Deployment",
        "web",
        spec={
            "selector": {
                "matchExpressions": [
                    {"key": "tier", "operator": "In", "values": ["backend"]}
                ]
            },
            "template": {"metadata": {"labels": {"app": "web"}}},
        },
    )
    graph = collect(
        [pod, deployment, obj("Service", "web", spec={"selector": {"app": "web"}})]
    )
    assert relationships(graph) == {
        ("k8s:prod:Service:web", "k8s:prod:Pod:web", "selects"),
        ("k8s:prod:Deployment:web", "k8s:prod:Pod:web", "manages"),
    }


def test_workload_config_secrets_storage_and_service_accounts():
    pod_spec = {
        "volumes": [
            {"configMap": {"name": "config"}},
            {"projected": {"sources": [{"secret": {"name": "secret"}}]}},
            {"persistentVolumeClaim": {"claimName": "data"}},
        ],
        "initContainers": [
            {
                "env": [
                    {"valueFrom": {"configMapKeyRef": {"name": "config", "key": "a"}}}
                ]
            }
        ],
        "containers": [{"envFrom": [{"secretRef": {"name": "secret"}}]}],
        "serviceAccountName": "worker",
        "imagePullSecrets": [{"name": "secret"}],
    }
    job = obj(
        "CronJob",
        "backup",
        spec={"jobTemplate": {"spec": {"template": {"spec": pod_spec}}}},
    )
    graph = collect(
        [
            job,
            obj("ConfigMap", "config"),
            obj("Secret", "secret"),
            obj("PersistentVolumeClaim", "data"),
            obj("ServiceAccount", "worker"),
        ]
    )
    assert {(edge.dst.split(":")[-2], edge.rel) for edge in graph.edges} == {
        ("ConfigMap", "mounts"),
        ("ConfigMap", "reads"),
        ("Secret", "mounts"),
        ("Secret", "reads"),
        ("Secret", "pulls_with"),
        ("PersistentVolumeClaim", "uses"),
        ("ServiceAccount", "uses"),
    }
    assert not graph.metadata["warnings"]


def test_ingress_hpa_storage_rbac_and_list_documents():
    docs = [
        obj("Service", "web"),
        obj("Deployment", "web"),
        obj("Secret", "tls"),
        obj(
            "Ingress",
            "entry",
            spec={
                "defaultBackend": {"service": {"name": "web"}},
                "tls": [{"secretName": "tls"}],
            },
        ),
        obj(
            "HorizontalPodAutoscaler",
            "web",
            spec={"scaleTargetRef": {"kind": "Deployment", "name": "web"}},
        ),
        obj(
            "PersistentVolumeClaim",
            "data",
            spec={"volumeName": "disk", "storageClassName": "fast"},
        ),
        obj("PersistentVolume", "disk"),
        obj("StorageClass", "fast"),
        obj("ClusterRole", "read"),
        obj("ServiceAccount", "reader"),
        obj(
            "RoleBinding",
            "read",
            roleRef={"kind": "ClusterRole", "name": "read"},
            subjects=[{"kind": "ServiceAccount", "name": "reader"}],
        ),
    ]
    graph = collect([{"kind": "List", "items": docs}])
    assert {edge.rel for edge in graph.edges} == {
        "routes_to",
        "uses_tls",
        "scales",
        "bound_to",
        "provisioned_by",
        "binds_role",
        "binds_subject",
    }
    assert "k8s:_cluster:PersistentVolume:disk" in {node.id for node in graph.nodes}
    assert not graph.metadata["warnings"]


def test_missing_references_do_not_create_phantom_nodes_or_edges():
    graph = collect(
        [obj("Pod", "web", spec={"volumes": [{"secret": {"secretName": "missing"}}]})]
    )
    assert len(graph.nodes) == 1
    assert not graph.edges
    assert "missing" in graph.metadata["warnings"][0]


def test_partial_files_and_stable_relationship_order(tmp_path):
    valid = tmp_path / "good.yaml"
    valid.write_text("kind: ConfigMap\nmetadata:\n  name: settings\n")
    invalid = tmp_path / "bad.yaml"
    invalid.write_text("kind: [invalid")
    graph = collect_from_kubernetes([invalid, valid], False)
    assert len(graph.nodes) == 1
    assert "bad.yaml" in graph.metadata["warnings"][0]
    assert (
        relationships(collect([obj("Service", "svc"), obj("ConfigMap", "cm")])) == set()
    )
