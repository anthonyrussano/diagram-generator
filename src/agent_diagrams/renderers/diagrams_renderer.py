from __future__ import annotations

import base64
import importlib
import re
from pathlib import Path

from agent_diagrams.model import GraphData

try:
    from diagrams import Diagram, Edge
    from diagrams.generic.blank import Blank
    DIAGRAMS_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependent
    Diagram = Edge = Blank = None
    DIAGRAMS_IMPORT_ERROR = exc

ICON_ALIASES = {
    "aws.alb": "diagrams.aws.network.ALB",
    "aws.elb": "diagrams.aws.network.ELB",
    "aws.vpc": "diagrams.aws.network.VPC",
    "aws.subnet.private": "diagrams.aws.network.PrivateSubnet",
    "aws.subnet.public": "diagrams.aws.network.PublicSubnet",
    "aws.tgw": "diagrams.aws.network.TransitGateway",
    "aws.directconnect": "diagrams.aws.network.DirectConnect",
    "aws.nacl": "diagrams.aws.network.Nacl",
    "aws.nat": "diagrams.aws.network.NATGateway",
    "aws.igw": "diagrams.aws.network.InternetGateway",
    "aws.route53": "diagrams.aws.network.Route53",
    "aws.cloudfront": "diagrams.aws.network.CloudFront",
    "aws.endpoint": "diagrams.aws.network.Endpoint",
    "aws.ec2": "diagrams.aws.compute.EC2",
    "aws.lambda": "diagrams.aws.compute.Lambda",
    "aws.ecs": "diagrams.aws.compute.ECS",
    "aws.eks": "diagrams.aws.compute.EKS",
    "aws.rds": "diagrams.aws.database.RDS",
    "aws.dynamodb": "diagrams.aws.database.Dynamodb",
    "aws.elasticache": "diagrams.aws.database.Elasticache",
    "aws.redshift": "diagrams.aws.database.Redshift",
    "aws.s3": "diagrams.aws.storage.S3",
    "aws.efs": "diagrams.aws.storage.EFS",
    "aws.ebs": "diagrams.aws.storage.EBS",
    "aws.sqs": "diagrams.aws.integration.SQS",
    "aws.sns": "diagrams.aws.integration.SNS",
    "aws.kinesis": "diagrams.aws.analytics.Kinesis",
    "aws.shield": "diagrams.aws.security.Shield",
    "aws.waf": "diagrams.aws.security.WAF",
    "aws.acm": "diagrams.aws.security.CertificateManager",
    "aws.iam": "diagrams.aws.security.IAM",
    "aws.iam.role": "diagrams.aws.security.IAMRole",
    "aws.secretsmanager": "diagrams.aws.security.SecretsManager",
    "aws.ssm": "diagrams.aws.management.SystemsManagerParameterStore",
    "aws.cloudwatch": "diagrams.aws.management.Cloudwatch",
    "aws.sg": "diagrams.generic.network.Firewall",
    "k8s.deploy": "diagrams.k8s.compute.Deployment",
    "k8s.pod": "diagrams.k8s.compute.Pod",
    "k8s.job": "diagrams.k8s.compute.Job",
    "k8s.cronjob": "diagrams.k8s.compute.Cronjob",
    "k8s.secret": "diagrams.k8s.podconfig.Secret",
    "k8s.configmap": "diagrams.k8s.podconfig.ConfigMap",
    "k8s.pv": "diagrams.k8s.storage.PersistentVolume",
    "k8s.pvc": "diagrams.k8s.storage.PersistentVolumeClaim",
    "k8s.ingress": "diagrams.k8s.network.Ingress",
    "k8s.svc": "diagrams.k8s.network.Service",
    "k8s.sa": "diagrams.k8s.rbac.ServiceAccount",
    "k8s.helm": "diagrams.k8s.ecosystem.Helm",
    "k8s.extdns": "diagrams.k8s.ecosystem.ExternalDns",
    "k8s.crd": "diagrams.k8s.others.CRD",
    "azure.activedirectory": "diagrams.azure.identity.ActiveDirectory",
    "azure.entra": "diagrams.azure.identity.ActiveDirectory",
    "network": "diagrams.onprem.network.Internet",
    "internet": "diagrams.onprem.network.Internet",
    "user": "diagrams.onprem.client.User",
    "users": "diagrams.onprem.client.Users",
    "generic.firewall": "diagrams.generic.network.Firewall",
    "generic.rack": "diagrams.generic.compute.Rack",
    "generic.blank": "diagrams.generic.blank.Blank",
    "onprem.user": "diagrams.onprem.client.User",
    "onprem.client": "diagrams.onprem.client.Client",
    "onprem.users": "diagrams.onprem.client.Users",
    "onprem.prometheus": "diagrams.onprem.monitoring.Prometheus",
    "onprem.grafana": "diagrams.onprem.monitoring.Grafana",
    "onprem.vault": "diagrams.onprem.security.Vault",
    "onprem.githubactions": "diagrams.onprem.ci.GithubActions",
    "onprem.terraform": "diagrams.onprem.iac.Terraform",
    "onprem.github": "diagrams.onprem.vcs.Github",
    # Short-name aliases for common bare kind values (e.g. from JSON graph files)
    "deployment": "diagrams.k8s.compute.Deployment",
    "pod": "diagrams.k8s.compute.Pod",
    "service": "diagrams.k8s.network.Service",
    "ingress": "diagrams.k8s.network.Ingress",
    "secret": "diagrams.k8s.podconfig.Secret",
    "configmap": "diagrams.k8s.podconfig.ConfigMap",
    "namespace": "diagrams.k8s.compute.Deployment",
    "serviceaccount": "diagrams.k8s.rbac.ServiceAccount",
    "loadbalancer": "diagrams.aws.network.ALB",
    "database": "diagrams.aws.database.RDS",
    "storage": "diagrams.aws.storage.S3",
    "dns": "diagrams.aws.network.Route53",
    "certificate": "diagrams.aws.security.CertificateManager",
    "monitoring": "diagrams.onprem.monitoring.Prometheus",
    "security": "diagrams.generic.network.Firewall",
    "auth": "diagrams.aws.security.IAM",
    "iam": "diagrams.aws.security.IAM",
    "actor": "diagrams.onprem.client.User",
}

DEFAULT_GRAPH_ATTR = {
    "splines": "spline",
    "ranksep": "1.0",
    "nodesep": "0.75",
    "pad": "0.4",
}


def _require_diagrams() -> None:
    if DIAGRAMS_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Non-Mermaid rendering requested, but the 'diagrams' package is not installed. "
            f"Install it first (original import error: {DIAGRAMS_IMPORT_ERROR})."
        )


def _dotted_import(path: str):
    module_name, cls_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)


def _resolve_icon(kind: str, label: str, node_id: str):
    _require_diagrams()
    kind_key = kind.strip().lower()
    alias = ICON_ALIASES.get(kind_key)
    if not alias:
        label_key = label.strip().lower()
        node_key = node_id.strip().lower()
        if "security group" in label_key or kind_key.endswith(".sg") or node_key.startswith("sg"):
            alias = "diagrams.generic.network.Firewall"
        elif label_key == "internet" or "internet" in label_key:
            alias = "diagrams.onprem.network.Internet"
        elif "user" in label_key:
            alias = "diagrams.onprem.client.Users"
    if not alias:
        return Blank
    try:
        return _dotted_import(alias)
    except Exception:
        return Blank


def _inline_svg_image_refs(svg_path: Path) -> None:
    raw = svg_path.read_text(encoding="utf-8")
    pattern = re.compile(r'(xlink:href|href)="([^"]+)"')

    def replace(match: re.Match[str]) -> str:
        attr = match.group(1)
        href = match.group(2)
        if href.startswith("data:"):
            return match.group(0)
        icon_path = Path(href)
        if not icon_path.is_file():
            return match.group(0)

        suffix = icon_path.suffix.lower()
        if suffix not in {".png", ".svg"}:
            return match.group(0)

        mime = "image/png" if suffix == ".png" else "image/svg+xml"
        encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
        return f'{attr}="data:{mime};base64,{encoded}"'

    updated = pattern.sub(replace, raw)
    svg_path.write_text(updated, encoding="utf-8")


def render_with_diagrams(
    graph: GraphData,
    output_prefix: Path,
    *,
    output_format: str = "png",
    direction: str = "LR",
    title: str = "Infrastructure Diagram",
) -> Path:
    _require_diagrams()

    graph_attr = dict(DEFAULT_GRAPH_ATTR)
    output_prefix = output_prefix.resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    node_objs: dict[str, object] = {}
    sorted_nodes = sorted(graph.nodes, key=lambda n: n.id)
    sorted_edges = sorted(graph.edges, key=lambda e: (e.src, e.dst, e.rel, e.source))

    with Diagram(
        title,
        filename=str(output_prefix),
        show=False,
        outformat=output_format,
        direction=direction,
        graph_attr=graph_attr,
    ):
        for node in sorted_nodes:
            icon_class = _resolve_icon(node.kind, node.label, node.id)
            node_objs[node.id] = icon_class(node.label)

        for edge in sorted_edges:
            src = node_objs.get(edge.src)
            dst = node_objs.get(edge.dst)
            if src is None or dst is None:
                continue
            src >> Edge(label=edge.rel) >> dst

    output_path = output_prefix.parent / f"{output_prefix.name}.{output_format}"
    if output_format == "svg":
        _inline_svg_image_refs(output_path)
    return output_path
