from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .model import Edge, GraphData, Node


def _run_json(cmd: list[str]) -> Any:
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def _run_text(cmd: list[str]) -> str:
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out.stdout or ""


def _safe_name(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return str(value)


def collect_from_aws_cli(profile: str, region: str) -> GraphData:
    graph = GraphData(metadata={"source": "aws", "profile": profile, "region": region})
    base = ["aws", "--profile", profile, "--region", region]

    vpcs = _run_json(base + ["ec2", "describe-vpcs"])
    subnets = _run_json(base + ["ec2", "describe-subnets"])
    instances = _run_json(base + ["ec2", "describe-instances"])
    lambdas = _run_json(base + ["lambda", "list-functions"])
    rds = _run_json(base + ["rds", "describe-db-instances"])
    albs = _run_json(base + ["elbv2", "describe-load-balancers"])
    s3 = _run_json(base + ["s3api", "list-buckets"])
    ddb = _run_json(base + ["dynamodb", "list-tables"])
    eks = _run_json(base + ["eks", "list-clusters"])
    ecs = _run_json(base + ["ecs", "list-clusters"])

    for v in vpcs.get("Vpcs", []):
        vid = v.get("VpcId", "unknown-vpc")
        graph.add_node(Node(id=f"aws:vpc:{vid}", label=vid, kind="aws.vpc", source="aws", attrs=v))

    for s in subnets.get("Subnets", []):
        sid = s.get("SubnetId", "unknown-subnet")
        vpc_id = s.get("VpcId")
        n = Node(id=f"aws:subnet:{sid}", label=sid, kind="aws.subnet", source="aws", attrs=s)
        graph.add_node(n)
        if vpc_id:
            graph.add_edge(Edge(src=n.id, dst=f"aws:vpc:{vpc_id}", rel="in", source="aws"))

    for r in instances.get("Reservations", []):
        for i in r.get("Instances", []):
            iid = i.get("InstanceId", "unknown-instance")
            sid = i.get("SubnetId")
            node = Node(id=f"aws:ec2:{iid}", label=iid, kind="aws.ec2", source="aws", attrs=i)
            graph.add_node(node)
            if sid:
                graph.add_edge(Edge(src=node.id, dst=f"aws:subnet:{sid}", rel="in", source="aws"))

    for fn in lambdas.get("Functions", []):
        arn = fn.get("FunctionArn", "unknown-lambda")
        node = Node(id=f"aws:lambda:{arn}", label=_safe_name(fn.get("FunctionName"), arn), kind="aws.lambda", source="aws", attrs=fn)
        graph.add_node(node)
        vpc_cfg = fn.get("VpcConfig", {})
        for sid in vpc_cfg.get("SubnetIds") or []:
            graph.add_edge(Edge(src=node.id, dst=f"aws:subnet:{sid}", rel="runs_in", source="aws"))

    for db in rds.get("DBInstances", []):
        dbid = db.get("DBInstanceIdentifier", "unknown-rds")
        node = Node(id=f"aws:rds:{dbid}", label=dbid, kind="aws.rds", source="aws", attrs=db)
        graph.add_node(node)
        for sn in db.get("DBSubnetGroup", {}).get("Subnets", []):
            sid = sn.get("SubnetIdentifier")
            if sid:
                graph.add_edge(Edge(src=node.id, dst=f"aws:subnet:{sid}", rel="in", source="aws"))

    for lb in albs.get("LoadBalancers", []):
        arn = lb.get("LoadBalancerArn", "unknown-alb")
        node = Node(id=f"aws:alb:{arn}", label=_safe_name(lb.get("LoadBalancerName"), arn), kind="aws.alb", source="aws", attrs=lb)
        graph.add_node(node)
        for az in lb.get("AvailabilityZones", []):
            sid = az.get("SubnetId")
            if sid:
                graph.add_edge(Edge(src=node.id, dst=f"aws:subnet:{sid}", rel="attached_to", source="aws"))

    for b in s3.get("Buckets", []):
        name = b.get("Name", "unknown-bucket")
        graph.add_node(Node(id=f"aws:s3:{name}", label=name, kind="aws.s3", source="aws", attrs=b))

    for t in ddb.get("TableNames", []):
        graph.add_node(Node(id=f"aws:dynamodb:{t}", label=t, kind="aws.dynamodb", source="aws"))

    for c in eks.get("clusters", []):
        graph.add_node(Node(id=f"aws:eks:{c}", label=c, kind="aws.eks", source="aws"))

    for arn in ecs.get("clusterArns", []):
        graph.add_node(Node(id=f"aws:ecs:{arn}", label=arn.split("/")[-1], kind="aws.ecs", source="aws"))

    return graph


def collect_from_json(paths: list[Path]) -> GraphData:
    graph = GraphData(metadata={"source": "json", "inputs": [str(p) for p in paths]})
    for path in paths:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and "nodes" in data:
            for n in data.get("nodes", []):
                graph.add_node(
                    Node(
                        id=str(n["id"]),
                        label=str(n.get("label", n["id"])),
                        kind=str(n.get("kind", "json.node")),
                        source="json",
                        attrs=n.get("attrs", {}),
                    )
                )
            for e in data.get("edges", []):
                graph.add_edge(
                    Edge(
                        src=str(e["src"]),
                        dst=str(e["dst"]),
                        rel=str(e.get("rel", "related_to")),
                        source="json",
                        attrs=e.get("attrs", {}),
                    )
                )
            continue

        root_id = f"json:file:{path.name}"
        graph.add_node(Node(id=root_id, label=path.name, kind="json.file", source="json", attrs={"path": str(path)}))
    return graph


def collect_from_terraform(paths: list[Path]) -> GraphData:
    graph = GraphData(metadata={"source": "terraform", "inputs": [str(p) for p in paths]})
    for path in paths:
        raw = json.loads(path.read_text())

        if "resources" in raw:  # state file shape
            for r in raw.get("resources", []):
                rtype = r.get("type", "resource")
                name = r.get("name", "unnamed")
                rid = f"tf:{rtype}.{name}"
                graph.add_node(Node(id=rid, label=f"{rtype}.{name}", kind=f"tf.{rtype}", source="terraform", attrs=r))
            continue

        if "resource" in raw:  # tf.json config shape
            for rtype, entries in raw.get("resource", {}).items():
                for name, attrs in entries.items():
                    rid = f"tf:{rtype}.{name}"
                    graph.add_node(Node(id=rid, label=f"{rtype}.{name}", kind=f"tf.{rtype}", source="terraform", attrs=attrs))

                    # basic ref extraction for explicit "depends_on"
                    for dep in attrs.get("depends_on", []):
                        graph.add_edge(Edge(src=rid, dst=f"tf:{dep}", rel="depends_on", source="terraform"))

    return graph


def collect_from_helm_charts(
    chart_paths: list[Path],
    values_files: list[Path],
    namespace: str,
    release_prefix: str,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for idx, chart in enumerate(chart_paths, start=1):
        release_name = f"{release_prefix}-{idx}"
        cmd = ["helm", "template", release_name, str(chart), "--namespace", namespace]
        for values_file in values_files:
            cmd.extend(["--values", str(values_file)])

        rendered = _run_text(cmd)
        for d in yaml.safe_load_all(rendered):
            if isinstance(d, dict):
                docs.append(d)
    return docs


def collect_from_kubernetes(
    manifest_paths: list[Path],
    use_live_cluster: bool,
    extra_docs: list[dict[str, Any]] | None = None,
) -> GraphData:
    graph = GraphData(metadata={"source": "kubernetes", "inputs": [str(p) for p in manifest_paths], "live": use_live_cluster})

    docs: list[dict[str, Any]] = []
    for path in manifest_paths:
        with path.open("r") as fh:
            for d in yaml.safe_load_all(fh):
                if isinstance(d, dict):
                    docs.append(d)

    if extra_docs:
        docs.extend(extra_docs)

    if use_live_cluster:
        live = _run_json(["kubectl", "get", "all", "--all-namespaces", "-o", "json"])
        docs.extend(live.get("items", []))

    for obj in docs:
        kind = obj.get("kind", "Unknown")
        meta = obj.get("metadata", {})
        ns = meta.get("namespace", "default")
        name = meta.get("name", "unnamed")
        node_id = f"k8s:{ns}:{kind}:{name}"

        graph.add_node(
            Node(
                id=node_id,
                label=f"{kind}/{name}",
                kind=f"k8s.{str(kind).lower()}",
                source="kubernetes",
                attrs=obj,
            )
        )

        owner_refs = meta.get("ownerReferences", []) or []
        for owner in owner_refs:
            ok = owner.get("kind", "Unknown")
            oname = owner.get("name", "unnamed")
            graph.add_edge(
                Edge(
                    src=node_id,
                    dst=f"k8s:{ns}:{ok}:{oname}",
                    rel="owned_by",
                    source="kubernetes",
                )
            )

    return graph


def discover_files(root: Path) -> dict[str, list[Path]]:
    return {
        "json": sorted([p for p in root.rglob("*.json") if p.is_file()]),
        "tfstate": sorted([p for p in root.rglob("*.tfstate") if p.is_file()]),
        "tfjson": sorted([p for p in root.rglob("*.tf.json") if p.is_file()]),
        "k8s": sorted(
            [
                p
                for p in root.rglob("*.y*ml")
                if p.is_file() and any(k in str(p).lower() for k in ["k8s", "kube", "manif", "chart"])
            ]
        ),
    }
