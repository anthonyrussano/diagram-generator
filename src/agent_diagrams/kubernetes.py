"""Relationships supported by observed Kubernetes manifests, without placeholders."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .model import Edge, GraphData, Node

CLUSTER_KINDS = {
    "Namespace",
    "Node",
    "PersistentVolume",
    "StorageClass",
    "ClusterRole",
    "ClusterRoleBinding",
    "CustomResourceDefinition",
    "IngressClass",
    "CSIDriver",
    "CSINode",
    "VolumeAttachment",
    "PriorityClass",
    "RuntimeClass",
}
WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}


def _flatten(docs: list[dict]) -> Iterator[dict]:
    for doc in docs:
        if doc.get("kind") == "List" or str(doc.get("kind", "")).endswith("List"):
            yield from _flatten(
                [item for item in doc.get("items", []) if isinstance(item, dict)]
            )
        else:
            yield doc


def _pod_spec(obj: dict) -> dict:
    spec = obj.get("spec") or {}
    if obj["kind"] == "Pod":
        return spec
    if obj["kind"] == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {}) if obj["kind"] in WORKLOADS else {}


def _pod_labels(obj: dict) -> dict:
    if obj["kind"] == "Pod":
        return obj.get("metadata", {}).get("labels") or {}
    spec = obj.get("spec") or {}
    if obj["kind"] == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("metadata", {}).get("labels") or {}


def _matches(selector: dict, labels: dict) -> bool:
    if not selector:
        return False
    required = selector.get("matchLabels", {})
    if any(labels.get(k) != v for k, v in required.items()):
        return False
    for expression in selector.get("matchExpressions", []):
        key, op, values = (
            expression.get("key"),
            expression.get("operator"),
            expression.get("values", []),
        )
        if op == "In" and (key not in labels or labels[key] not in values):
            return False
        if op == "NotIn" and labels.get(key) in values:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
        if op not in {"In", "NotIn", "Exists", "DoesNotExist"}:
            return False
    return True


def collect_kubernetes_objects(docs: list[dict], metadata: dict[str, Any]) -> GraphData:
    graph = GraphData(
        metadata={
            **metadata,
            "warnings": [],
            "relationship_detection": "manifest-references-v1",
        }
    )
    warnings: list[str] = graph.metadata["warnings"]
    objects: dict[tuple[str, str, str], dict] = {}

    def key(kind: str, name: str, namespace: str) -> tuple[str, str, str]:
        return ("_cluster" if kind in CLUSTER_KINDS else namespace, kind, name)

    def node_id(item_key: tuple[str, str, str]) -> str:
        return "k8s:" + ":".join(item_key)

    for obj in _flatten(docs):
        kind, meta = obj.get("kind"), obj.get("metadata") or {}
        if not kind or not meta.get("name"):
            warnings.append("Skipped document without Kubernetes kind/metadata.name.")
            continue
        item_key = key(kind, meta["name"], meta.get("namespace") or "default")
        if item_key in objects and objects[item_key] != obj:
            warnings.append(
                f"Conflicting definitions for {node_id(item_key)}; using the first definition."
            )
        objects.setdefault(item_key, obj)

    edges: dict[tuple[str, str, str], Edge] = {}

    def connect(
        source: tuple[str, str, str],
        target: tuple[str, str, str],
        rel: str,
        **attrs: Any,
    ) -> None:
        if target not in objects:
            warnings.append(
                f"{node_id(source)}: unresolved {rel} target {node_id(target)}."
            )
        elif source != target:
            identity = (node_id(source), node_id(target), rel)
            edges.setdefault(
                identity, Edge(*identity, source="kubernetes", attrs=attrs)
            )

    for item_key, obj in sorted(objects.items()):
        namespace, kind, name = item_key
        graph.add_node(
            Node(
                node_id(item_key),
                f"{kind}/{name}",
                f"k8s.{kind.lower()}",
                "kubernetes",
                obj,
            )
        )
        spec = obj.get("spec") or {}

        def ref(
            target_kind: str,
            target_name: str | None,
            rel: str,
            target_namespace: str = namespace,
            *,
            source_key: tuple[str, str, str] = item_key,
        ) -> None:
            if target_name:
                connect(source_key, key(target_kind, target_name, target_namespace), rel)

        for owner in obj.get("metadata", {}).get("ownerReferences") or []:
            ref(owner.get("kind", "Unknown"), owner.get("name"), "owned_by")

        if kind == "Service" and spec.get("selector"):
            selector = {"matchLabels": spec["selector"]}
            candidates = [
                (k, o)
                for k, o in objects.items()
                if k[0] == namespace
                and k[1] == "Pod"
                and _matches(selector, _pod_labels(o))
            ]
            if not candidates:
                candidates = [
                    (k, o)
                    for k, o in objects.items()
                    if k[0] == namespace
                    and k[1] in WORKLOADS
                    and _matches(selector, _pod_labels(o))
                ]
            for target_key, _ in candidates:
                connect(
                    item_key,
                    target_key,
                    "selects",
                    matched_on="pod_labels"
                    if target_key[1] == "Pod"
                    else "pod_template_labels",
                )
        elif kind in WORKLOADS and spec.get("selector"):
            for target_key, target in objects.items():
                if target_key[:2] == (namespace, "Pod") and _matches(
                    spec["selector"], _pod_labels(target)
                ):
                    connect(item_key, target_key, "manages")

        pod_spec = _pod_spec(obj)
        for volume in pod_spec.get("volumes") or []:
            ref("ConfigMap", (volume.get("configMap") or {}).get("name"), "mounts")
            ref("Secret", (volume.get("secret") or {}).get("secretName"), "mounts")
            ref(
                "PersistentVolumeClaim",
                (volume.get("persistentVolumeClaim") or {}).get("claimName"),
                "uses",
            )
            for projected in (volume.get("projected") or {}).get("sources") or []:
                ref(
                    "ConfigMap",
                    (projected.get("configMap") or {}).get("name"),
                    "mounts",
                )
                ref("Secret", (projected.get("secret") or {}).get("name"), "mounts")
        for container_type in ("containers", "initContainers", "ephemeralContainers"):
            for container in pod_spec.get(container_type) or []:
                for env_from in container.get("envFrom") or []:
                    ref(
                        "ConfigMap",
                        (env_from.get("configMapRef") or {}).get("name"),
                        "reads",
                    )
                    ref(
                        "Secret", (env_from.get("secretRef") or {}).get("name"), "reads"
                    )
                for env in container.get("env") or []:
                    value_from = env.get("valueFrom") or {}
                    ref(
                        "ConfigMap",
                        (value_from.get("configMapKeyRef") or {}).get("name"),
                        "reads",
                    )
                    ref(
                        "Secret",
                        (value_from.get("secretKeyRef") or {}).get("name"),
                        "reads",
                    )
        ref(
            "ServiceAccount",
            pod_spec.get("serviceAccountName") or pod_spec.get("serviceAccount"),
            "uses",
        )
        for image_secret in pod_spec.get("imagePullSecrets") or []:
            ref("Secret", image_secret.get("name"), "pulls_with")

        if kind == "Ingress":
            backends = [spec.get("defaultBackend") or spec.get("backend") or {}]
            for rule in spec.get("rules") or []:
                backends.extend(
                    path.get("backend") or {}
                    for path in (rule.get("http") or {}).get("paths") or []
                )
            for backend in backends:
                ref(
                    "Service",
                    (backend.get("service") or {}).get("name")
                    or backend.get("serviceName"),
                    "routes_to",
                )
                resource = backend.get("resource") or {}
                ref(resource.get("kind", "Unknown"), resource.get("name"), "routes_to")
            for tls in spec.get("tls") or []:
                ref("Secret", tls.get("secretName"), "uses_tls")
        if kind == "HorizontalPodAutoscaler":
            target = spec.get("scaleTargetRef") or {}
            ref(target.get("kind", "Unknown"), target.get("name"), "scales")
        if kind == "PersistentVolumeClaim":
            ref("PersistentVolume", spec.get("volumeName"), "bound_to")
            ref("StorageClass", spec.get("storageClassName"), "provisioned_by")
        if kind in {"RoleBinding", "ClusterRoleBinding"}:
            role = obj.get("roleRef") or {}
            ref(role.get("kind", "Unknown"), role.get("name"), "binds_role")
            for subject in obj.get("subjects") or []:
                if subject.get("kind") == "ServiceAccount":
                    subject_namespace = subject.get("namespace") or (
                        namespace if kind == "RoleBinding" else None
                    )
                    if subject_namespace:
                        ref(
                            "ServiceAccount",
                            subject.get("name"),
                            "binds_subject",
                            subject_namespace,
                        )
        if kind == "StatefulSet" and spec.get("volumeClaimTemplates"):
            warnings.append(
                f"{node_id(item_key)}: volumeClaimTemplates are not expanded into generated PVCs."
            )

    graph.edges = [edges[identity] for identity in sorted(edges)]
    graph.metadata["warnings"] = sorted(set(warnings))
    return graph
