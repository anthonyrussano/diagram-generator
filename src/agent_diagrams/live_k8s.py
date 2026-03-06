from __future__ import annotations

import copy
import json
import subprocess
from typing import Any


def _name_key(item: dict[str, Any]) -> str:
    return str(item.get("metadata", {}).get("name", ""))


def _kubectl(args: list[str], context: str | None = None) -> dict[str, Any]:
    cmd = ["kubectl"]
    if context:
        cmd.extend(["--context", context])
    cmd.extend(args)
    cmd.extend(["-o", "json"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"kubectl executable not found while running: {' '.join(cmd)}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "kubectl command failed\n"
            f"command: {' '.join(cmd)}\n"
            f"exit_code: {exc.returncode}\n"
            f"stdout:\n{exc.stdout or ''}\n"
            f"stderr:\n{exc.stderr or ''}"
        ) from exc
    return json.loads(result.stdout)


def get_namespace_state(
    namespace: str,
    context: str | None = None,
    resources: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if resources is None:
        resources = [
            "deployments",
            "pods",
            "services",
            "ingresses",
            "jobs",
            "persistentvolumeclaims",
            "externalsecrets",
        ]

    state: dict[str, list[dict[str, Any]]] = {}
    for resource in resources:
        try:
            payload = _kubectl(["get", resource, "-n", namespace], context)
            state[resource] = payload.get("items", [])
        except RuntimeError as exc:
            if "kubectl executable not found" in str(exc):
                raise
            state[resource] = []
    return state


def _deployment_status(dep: dict[str, Any]) -> str:
    replicas = dep.get("spec", {}).get("replicas", 1) or 1
    status = dep.get("status", {})
    ready = status.get("readyReplicas", 0) or 0
    if ready >= replicas:
        return "running"
    if ready > 0:
        return "degraded"
    return "failed"


def _pod_status(pod: dict[str, Any]) -> str:
    phase = pod.get("status", {}).get("phase", "Unknown")
    for container in pod.get("status", {}).get("containerStatuses", []):
        reason = container.get("state", {}).get("waiting", {}).get("reason", "")
        if reason == "CrashLoopBackOff":
            return "crashloop"
        if reason in {"Error", "OOMKilled", "CreateContainerError"}:
            return "failed"

    if phase == "Running":
        return "running"
    if phase == "Succeeded":
        return "healthy"
    if phase == "Failed":
        return "failed"
    if phase == "Pending":
        return "pending"
    return "unknown"


def _job_status(job: dict[str, Any]) -> str:
    status = job.get("status", {})
    if status.get("succeeded", 0):
        return "healthy"
    if status.get("active", 0):
        return "running"
    if status.get("failed", 0):
        return "failed"
    return "pending"


def _pvc_status(pvc: dict[str, Any]) -> str:
    phase = pvc.get("status", {}).get("phase", "Unknown")
    return "running" if phase == "Bound" else "failed"


def _externalsecret_status(external_secret: dict[str, Any]) -> str:
    for condition in external_secret.get("status", {}).get("conditions", []):
        if condition.get("type") == "Ready":
            return "running" if condition.get("status") == "True" else "failed"
    return "unknown"


def generate_namespace_spec(
    namespace: str,
    context: str | None = None,
    title: str | None = None,
    direction: str = "LR",
) -> dict[str, Any]:
    state = get_namespace_state(namespace, context)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    clusters = [{"id": "ns", "label": f"Namespace: {namespace}"}]

    for ingress in sorted(state.get("ingresses", []), key=_name_key):
        name = ingress.get("metadata", {}).get("name", "unnamed-ingress")
        hosts = [rule.get("host", "") for rule in ingress.get("spec", {}).get("rules", [])]
        load_balancers = [
            item.get("hostname") or item.get("ip", "")
            for item in ingress.get("status", {}).get("loadBalancer", {}).get("ingress", [])
        ]

        label = name
        if hosts:
            label += "\n" + ", ".join(host for host in hosts if host)
        if load_balancers:
            label += "\n-> " + load_balancers[0]

        nodes.append(
            {
                "id": f"ing_{name}",
                "label": label,
                "icon": "k8s.ingress",
                "cluster": "ns",
                "k8s_resource": {"namespace": namespace, "kind": "ingress", "name": name},
            }
        )

    for service in sorted(state.get("services", []), key=_name_key):
        name = service.get("metadata", {}).get("name", "unnamed-service")
        ports = ", ".join(
            f"{port.get('port')}/{port.get('protocol', 'TCP')}"
            for port in service.get("spec", {}).get("ports", [])
        )
        nodes.append(
            {
                "id": f"svc_{name}",
                "label": f"{name}\n({ports})",
                "icon": "k8s.svc",
                "cluster": "ns",
                "k8s_resource": {"namespace": namespace, "kind": "service", "name": name},
            }
        )

    for deployment in sorted(state.get("deployments", []), key=_name_key):
        name = deployment.get("metadata", {}).get("name", "unnamed-deployment")
        status = _deployment_status(deployment)
        desired = deployment.get("spec", {}).get("replicas", 1) or 1
        ready = deployment.get("status", {}).get("readyReplicas", 0) or 0
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])

        image_tag = ""
        if containers:
            image = containers[0].get("image", "")
            image_tag = image.split(":")[-1] if ":" in image else image.split("/")[-1]

        label = f"{name}\n{ready}/{desired} ready"
        if image_tag:
            label += f"\n{image_tag}"

        nodes.append(
            {
                "id": f"deploy_{name}",
                "label": label,
                "icon": "k8s.deploy",
                "cluster": "ns",
                "status": status,
                "k8s_resource": {"namespace": namespace, "kind": "deployment", "name": name},
            }
        )

    for job in sorted(state.get("jobs", []), key=_name_key):
        name = job.get("metadata", {}).get("name", "unnamed-job")
        status = _job_status(job)
        if status == "healthy":
            continue

        raw = job.get("status", {})
        label = f"{name}\nactive:{raw.get('active', 0)} ok:{raw.get('succeeded', 0)} fail:{raw.get('failed', 0)}"
        nodes.append(
            {
                "id": f"job_{name}",
                "label": label,
                "icon": "k8s.job",
                "cluster": "ns",
                "status": status,
                "k8s_resource": {"namespace": namespace, "kind": "job", "name": name},
            }
        )

    for pvc in sorted(state.get("persistentvolumeclaims", []), key=_name_key):
        name = pvc.get("metadata", {}).get("name", "unnamed-pvc")
        status = _pvc_status(pvc)
        capacity = pvc.get("status", {}).get("capacity", {}).get("storage", "")
        storage_class = pvc.get("spec", {}).get("storageClassName", "")

        label = f"{name}\n{capacity}"
        if storage_class:
            label += f"\n({storage_class})"

        nodes.append(
            {
                "id": f"pvc_{name}",
                "label": label,
                "icon": "k8s.pvc",
                "cluster": "ns",
                "status": status,
                "k8s_resource": {"namespace": namespace, "kind": "persistentvolumeclaim", "name": name},
            }
        )

    for external_secret in sorted(state.get("externalsecrets", []), key=_name_key):
        name = external_secret.get("metadata", {}).get("name", "unnamed-external-secret")
        status = _externalsecret_status(external_secret)
        target = external_secret.get("spec", {}).get("target", {}).get("name", name)

        nodes.append(
            {
                "id": f"es_{name}",
                "label": f"{name}\n-> secret: {target}",
                "icon": "k8s.secret",
                "cluster": "ns",
                "status": status,
                "k8s_resource": {"namespace": namespace, "kind": "externalsecret", "name": name},
            }
        )

    node_ids = {node["id"] for node in nodes}

    for ingress in sorted(state.get("ingresses", []), key=_name_key):
        ingress_name = ingress.get("metadata", {}).get("name", "")
        ingress_id = f"ing_{ingress_name}"
        for rule in ingress.get("spec", {}).get("rules", []):
            for path in rule.get("http", {}).get("paths", []):
                service_name = path.get("backend", {}).get("service", {}).get("name", "")
                if service_name and f"svc_{service_name}" in node_ids:
                    edges.append({"from": ingress_id, "to": f"svc_{service_name}"})

    for service in sorted(state.get("services", []), key=_name_key):
        service_name = service.get("metadata", {}).get("name", "")
        service_id = f"svc_{service_name}"
        selector = service.get("spec", {}).get("selector", {})

        for deployment in sorted(state.get("deployments", []), key=_name_key):
            labels = deployment.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
            if selector and all(labels.get(key) == value for key, value in selector.items()):
                deployment_name = deployment.get("metadata", {}).get("name", "")
                edges.append({"from": service_id, "to": f"deploy_{deployment_name}"})

    stable_nodes = sorted(nodes, key=lambda node: str(node.get("id", "")))
    stable_edges = sorted(
        edges,
        key=lambda edge: (
            str(edge.get("from", "")),
            str(edge.get("to", "")),
            str(edge.get("label", "")),
        ),
    )

    return {
        "title": title or f"K8s Live State: {namespace}",
        "direction": direction,
        "graph_attr": {"ranksep": "1.0", "nodesep": "0.7", "splines": "ortho"},
        "clusters": clusters,
        "nodes": stable_nodes,
        "edges": stable_edges,
    }


def _collect_live_state(namespaces: list[str], context: str | None) -> dict[tuple[str, str, str], str]:
    lookup: dict[tuple[str, str, str], str] = {}
    for namespace in namespaces:
        try:
            state = get_namespace_state(namespace, context)
        except Exception as exc:  # pragma: no cover - subprocess/env dependent
            print(f"  [k8s] Warning: could not query namespace '{namespace}': {exc}")
            continue

        for deployment in sorted(state.get("deployments", []), key=_name_key):
            name = deployment.get("metadata", {}).get("name", "")
            lookup[(namespace, "deployment", name)] = _deployment_status(deployment)

        for pod in sorted(state.get("pods", []), key=_name_key):
            name = pod.get("metadata", {}).get("name", "")
            lookup[(namespace, "pod", name)] = _pod_status(pod)

        for job in sorted(state.get("jobs", []), key=_name_key):
            name = job.get("metadata", {}).get("name", "")
            lookup[(namespace, "job", name)] = _job_status(job)

        for pvc in sorted(state.get("persistentvolumeclaims", []), key=_name_key):
            name = pvc.get("metadata", {}).get("name", "")
            lookup[(namespace, "persistentvolumeclaim", name)] = _pvc_status(pvc)

        for external_secret in sorted(state.get("externalsecrets", []), key=_name_key):
            name = external_secret.get("metadata", {}).get("name", "")
            lookup[(namespace, "externalsecret", name)] = _externalsecret_status(external_secret)

    return lookup


def annotate_spec(
    spec: dict[str, Any],
    namespaces: list[str] | None = None,
    context: str | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(spec)

    if not namespaces:
        namespaces = list(
            {
                node["k8s_resource"]["namespace"]
                for node in updated.get("nodes", [])
                if isinstance(node.get("k8s_resource"), dict) and node["k8s_resource"].get("namespace")
            }
        )

    if not namespaces:
        print("  [k8s] No namespaces specified or discoverable from spec; skipping annotation.")
        return updated

    print(f"  [k8s] Querying namespaces: {namespaces}")
    lookup = _collect_live_state(namespaces, context)
    fuzzy = {name: status for (_namespace, _kind, name), status in lookup.items()}

    for node in updated.get("nodes", []):
        status: str | None = None

        resource = node.get("k8s_resource")
        if isinstance(resource, dict):
            key = (
                str(resource.get("namespace", "")),
                str(resource.get("kind", "")),
                str(resource.get("name", "")),
            )
            status = lookup.get(key)

        if status is None:
            node_id = str(node.get("id", ""))
            node_label = str(node.get("label", ""))
            for name, matched_status in fuzzy.items():
                if name and (name in node_id or name in node_label):
                    status = matched_status
                    break

        if status is None:
            continue

        node["status"] = status
        lines = [line for line in str(node.get("label", "")).split("\n") if not line.startswith("[live:")]
        lines.append(f"[live: {status}]")
        node["label"] = "\n".join(lines)

    return updated


def summarize_namespace(namespace: str, context: str | None = None) -> dict[str, Any]:
    state = get_namespace_state(namespace, context)
    summary: dict[str, Any] = {"namespace": namespace, "deployments": [], "jobs": [], "pvcs": []}

    for deployment in sorted(state.get("deployments", []), key=_name_key):
        name = deployment.get("metadata", {}).get("name", "")
        replicas = deployment.get("spec", {}).get("replicas", 1) or 1
        ready = deployment.get("status", {}).get("readyReplicas", 0) or 0
        containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        image = containers[0].get("image", "") if containers else ""

        summary["deployments"].append(
            {
                "name": name,
                "ready": ready,
                "desired": replicas,
                "status": _deployment_status(deployment),
                "image": image,
            }
        )

    for job in sorted(state.get("jobs", []), key=_name_key):
        raw = job.get("status", {})
        summary["jobs"].append(
            {
                "name": job.get("metadata", {}).get("name", ""),
                "status": _job_status(job),
                "active": raw.get("active", 0),
                "succeeded": raw.get("succeeded", 0),
                "failed": raw.get("failed", 0),
            }
        )

    for pvc in sorted(state.get("persistentvolumeclaims", []), key=_name_key):
        summary["pvcs"].append(
            {
                "name": pvc.get("metadata", {}).get("name", ""),
                "status": _pvc_status(pvc),
                "capacity": pvc.get("status", {}).get("capacity", {}).get("storage", ""),
                "phase": pvc.get("status", {}).get("phase", ""),
            }
        )

    return summary
