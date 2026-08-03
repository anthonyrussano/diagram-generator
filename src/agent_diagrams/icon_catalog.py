from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ASSET_ICON_PREFIX = "asset:"
ICON_ASSET_DIR = Path(__file__).parent / "assets" / "icons"

# Discovery order only; it has no effect on alias resolution. A short class
# name (e.g. "Firewall") that exists under more than one provider is never
# given a short-name alias at all (see _builtin_aliases) rather than being
# resolved via provider precedence, since guessing the wrong provider's icon
# would be more misleading than falling back to canonical
# provider.category.icon names, which are always unambiguous.
DIAGRAM_PROVIDER_ORDER = (
    "programming",
    "saas",
    "onprem",
    "k8s",
    "aws",
    "azure",
    "gcp",
    "alibabacloud",
    "digitalocean",
    "elastic",
    "firebase",
    "ibm",
    "oci",
    "openstack",
    "outscale",
    "generic",
    "gis",
    "c4",
)


# Stable aliases used by collectors, specs, and common human-written graph kinds.
# The dynamic catalog below additionally exposes every public icon shipped by the
# installed diagrams package as provider.category.icon.
ICON_ALIASES: dict[str, str] = {
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
    "k8s.deployment": "diagrams.k8s.compute.Deployment",
    "k8s.pod": "diagrams.k8s.compute.Pod",
    "k8s.job": "diagrams.k8s.compute.Job",
    "k8s.cronjob": "diagrams.k8s.compute.Cronjob",
    "k8s.secret": "diagrams.k8s.podconfig.Secret",
    "k8s.configmap": "diagrams.k8s.podconfig.ConfigMap",
    "k8s.pv": "diagrams.k8s.storage.PersistentVolume",
    "k8s.pvc": "diagrams.k8s.storage.PersistentVolumeClaim",
    "k8s.ingress": "diagrams.k8s.network.Ingress",
    "k8s.svc": "diagrams.k8s.network.Service",
    "k8s.service": "diagrams.k8s.network.Service",
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
    "cloudflare": "diagrams.saas.cdn.Cloudflare",
    "cloudflare.cdn": "diagrams.saas.cdn.Cloudflare",
    "cloudflare.dns": "diagrams.saas.cdn.Cloudflare",
    "supabase": f"{ASSET_ICON_PREFIX}supabase.png",
    "supabase.auth": f"{ASSET_ICON_PREFIX}supabase.png",
    "supabase.database": f"{ASSET_ICON_PREFIX}supabase.png",
    "supabase.edge": f"{ASSET_ICON_PREFIX}supabase.png",
    "supabase.functions": f"{ASSET_ICON_PREFIX}supabase.png",
    "supabase.storage": f"{ASSET_ICON_PREFIX}supabase.png",
    "custom.supabase.supabase": f"{ASSET_ICON_PREFIX}supabase.png",
    "github.actions": "diagrams.onprem.ci.GithubActions",
    "githubactions": "diagrams.onprem.ci.GithubActions",
    "gitlab.ci": "diagrams.onprem.ci.GitlabCI",
    "gitlabci": "diagrams.onprem.ci.GitlabCI",
    "googlecloud": "diagrams.gcp.compute.ComputeEngine",
    "gcp": "diagrams.gcp.compute.ComputeEngine",
    "postgres": "diagrams.onprem.database.PostgreSQL",
    "postgresql": "diagrams.onprem.database.PostgreSQL",
    "mongo": "diagrams.onprem.database.MongoDB",
    "mongodb": "diagrams.onprem.database.MongoDB",
    "docker": "diagrams.onprem.container.Docker",
    "kubernetes": "diagrams.k8s.compute.Pod",
    "k8s": "diagrams.k8s.compute.Pod",
    "node": "diagrams.programming.language.NodeJS",
    "nodejs": "diagrams.programming.language.NodeJS",
    "js": "diagrams.programming.language.JavaScript",
    "javascript": "diagrams.programming.language.JavaScript",
    "ts": "diagrams.programming.language.TypeScript",
    "typescript": "diagrams.programming.language.TypeScript",
    "golang": "diagrams.programming.language.Go",
    "c++": "diagrams.programming.language.Cpp",
    "c#": "diagrams.programming.language.Csharp",
    ".net": "diagrams.programming.framework.DotNet",
    "dotnet": "diagrams.programming.framework.DotNet",
    "next": "diagrams.programming.framework.NextJs",
    "next.js": "diagrams.programming.framework.NextJs",
    "nextjs": "diagrams.programming.framework.NextJs",
    "fastapi": "diagrams.programming.framework.FastAPI",
    "graphql": "diagrams.programming.framework.GraphQL",
    "github": "diagrams.onprem.vcs.Github",
    "gitlab": "diagrams.onprem.vcs.Gitlab",
    "terraform": "diagrams.onprem.iac.Terraform",
    "argocd": "diagrams.onprem.gitops.ArgoCD",
    "prometheus": "diagrams.onprem.monitoring.Prometheus",
    "grafana": "diagrams.onprem.monitoring.Grafana",
    "datadog": "diagrams.saas.logging.Datadog",
    "newrelic": "diagrams.saas.logging.NewRelic",
    "elasticsearch": "diagrams.elastic.elasticsearch.Elasticsearch",
    "logstash": "diagrams.elastic.elasticsearch.Logstash",
    "kibana": "diagrams.elastic.elasticsearch.Kibana",
    "deployment": "diagrams.k8s.compute.Deployment",
    "pod": "diagrams.k8s.compute.Pod",
    "service": "diagrams.k8s.network.Service",
    "ingress": "diagrams.k8s.network.Ingress",
    "secret": "diagrams.k8s.podconfig.Secret",
    "configmap": "diagrams.k8s.podconfig.ConfigMap",
    "namespace": "diagrams.k8s.compute.Deployment",
    "serviceaccount": "diagrams.k8s.rbac.ServiceAccount",
    "loadbalancer": "diagrams.aws.network.ALB",
    "database": "diagrams.programming.flowchart.Database",
    "storage": "diagrams.programming.flowchart.StoredData",
    "file": "diagrams.programming.flowchart.Document",
    "document": "diagrams.programming.flowchart.Document",
    "dns": "diagrams.onprem.dns.Coredns",
    "certificate": "diagrams.onprem.certificates.CertManager",
    "monitoring": "diagrams.onprem.monitoring.Prometheus",
    "security": "diagrams.generic.network.Firewall",
    "auth": "diagrams.saas.identity.Auth0",
    "iam": "diagrams.aws.security.IAM",
    "actor": "diagrams.onprem.client.User",
}


# Words that are legitimate exact `kind`/`label` values (a JSON node with
# kind: "user" should still render a person icon) but resolve to a specific
# person icon or a single presumed third-party vendor brand, so they are too
# high-risk to award to one word buried inside a longer, human-written label.
# Without this guard, "User Authentication Service" or "Users API" matches the
# word "user(s)" before ever considering "service"/"api", silently rendering a
# backend service as a person icon; "auth-service" gets branded with the Auth0
# logo though it may not use Auth0 at all. Other generic infra nouns (e.g.
# "security", "database", "storage") are deliberately left out of this set:
# they resolve to generic concept icons, not a specific person or vendor, so
# matching them as a token (e.g. "security" inside "aws_security_group") is
# still a reasonable, non-misleading guess. These keys only resolve on a
# full-string match; they are skipped by the per-token fallback below.
GENERIC_KIND_ONLY_ALIASES = frozenset(
    {
        "user",
        "users",
        "actor",
        "auth",
        "iam",
    }
)


FILE_EXTENSION_ICONS = {
    ".bash": "diagrams.programming.language.Bash",
    ".c": "diagrams.programming.language.C",
    ".cc": "diagrams.programming.language.Cpp",
    ".cpp": "diagrams.programming.language.Cpp",
    ".cs": "diagrams.programming.language.Csharp",
    ".dart": "diagrams.programming.language.Dart",
    ".ex": "diagrams.programming.language.Elixir",
    ".exs": "diagrams.programming.language.Elixir",
    ".go": "diagrams.programming.language.Go",
    ".java": "diagrams.programming.language.Java",
    ".js": "diagrams.programming.language.JavaScript",
    ".jsx": "diagrams.programming.framework.React",
    ".kt": "diagrams.programming.language.Kotlin",
    ".kts": "diagrams.programming.language.Kotlin",
    ".php": "diagrams.programming.language.PHP",
    ".py": "diagrams.programming.language.Python",
    ".r": "diagrams.programming.language.R",
    ".rb": "diagrams.programming.language.Ruby",
    ".rs": "diagrams.programming.language.Rust",
    ".scala": "diagrams.programming.language.Scala",
    ".sh": "diagrams.programming.language.Bash",
    ".sql": "diagrams.programming.language.Sql",
    ".swift": "diagrams.programming.language.Swift",
    ".ts": "diagrams.programming.language.TypeScript",
    ".tsx": "diagrams.programming.framework.React",
    ".vue": "diagrams.programming.framework.Vue",
}


@dataclass(frozen=True, slots=True)
class IconInfo:
    name: str
    path: str
    provider: str
    category: str


def normalize_icon_key(value: str) -> str:
    value = value.casefold().replace("+", "plus").replace("#", "sharp")
    segments = re.split(r"[.:/\\]+", value.strip())
    normalized = [re.sub(r"[^a-z0-9]+", "", segment) for segment in segments]
    return ".".join(segment for segment in normalized if segment)


@lru_cache(maxsize=1)
def discover_builtin_icons() -> tuple[IconInfo, ...]:
    icons: list[IconInfo] = []
    for provider in DIAGRAM_PROVIDER_ORDER:
        package_name = f"diagrams.{provider}"
        try:
            package = importlib.import_module(package_name)
        except (ImportError, AttributeError):
            continue

        package_path = getattr(package, "__path__", None)
        if package_path is None:
            continue

        modules = sorted(pkgutil.walk_packages(package_path, f"{package_name}."), key=lambda item: item.name)
        for module_info in modules:
            try:
                module = importlib.import_module(module_info.name)
            except (ImportError, AttributeError):
                continue

            category = module_info.name.removeprefix(f"{package_name}.")
            for class_name, icon_class in sorted(vars(module).items()):
                if class_name.startswith("_"):
                    continue
                if not inspect.isclass(icon_class) or icon_class.__module__ != module.__name__:
                    continue
                name = f"{provider}.{category}.{class_name}"
                icons.append(
                    IconInfo(
                        name=name,
                        path=f"{module.__name__}.{class_name}",
                        provider=provider,
                        category=category,
                    )
                )

    return tuple(sorted(icons, key=lambda icon: (icon.name.casefold(), icon.name)))


@lru_cache(maxsize=1)
def _normalized_explicit_aliases() -> dict[str, str]:
    return {normalize_icon_key(alias): path for alias, path in ICON_ALIASES.items()}


@lru_cache(maxsize=1)
def _builtin_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    short_names: dict[str, list[IconInfo]] = {}
    provider_names: dict[str, list[IconInfo]] = {}

    for icon in discover_builtin_icons():
        canonical_key = normalize_icon_key(icon.name)
        aliases.setdefault(canonical_key, icon.path)
        aliases.setdefault(normalize_icon_key(f"diagrams.{icon.name}"), icon.path)

        class_name = icon.name.rsplit(".", 1)[-1]
        short_names.setdefault(normalize_icon_key(class_name), []).append(icon)
        provider_names.setdefault(normalize_icon_key(f"{icon.provider}.{class_name}"), []).append(icon)

    for grouped in (short_names, provider_names):
        for key, matches in grouped.items():
            unique_paths = sorted({match.path for match in matches})
            if len(unique_paths) == 1:
                aliases.setdefault(key, unique_paths[0])

    return aliases


def _lookup_named_icon(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith(ASSET_ICON_PREFIX) and resolve_asset_path(raw) is not None:
        return raw

    key = normalize_icon_key(raw)
    explicit = _normalized_explicit_aliases()
    if key in explicit:
        return explicit[key]

    builtins = _builtin_aliases()
    if key in builtins:
        return builtins[key]

    tokens = [normalize_icon_key(token) for token in re.split(r"[^a-zA-Z0-9+#]+", raw) if token]
    for token in tokens:
        if token in GENERIC_KIND_ONLY_ALIASES:
            continue
        if token in explicit:
            return explicit[token]
        if token in builtins:
            return builtins[token]
    return None


def resolve_node_icon(
    kind: str,
    label: str,
    node_id: str,
    *,
    explicit_icon: str | None = None,
) -> str | None:
    if explicit_icon:
        return _lookup_named_icon(explicit_icon)

    suffix = Path(label.strip()).suffix.casefold()
    if suffix in FILE_EXTENSION_ICONS:
        return FILE_EXTENSION_ICONS[suffix]

    for candidate in (kind, label, node_id):
        resolved = _lookup_named_icon(candidate)
        if resolved:
            return resolved
    return None


def resolve_spec_icon(icon: str | None) -> str | None:
    if not icon:
        return None
    return _lookup_named_icon(icon)


def resolve_asset_path(icon_ref: str) -> Path | None:
    if not icon_ref.startswith(ASSET_ICON_PREFIX):
        return None
    relative_path = icon_ref.removeprefix(ASSET_ICON_PREFIX)
    path = (ICON_ASSET_DIR / relative_path).resolve()
    if path.parent != ICON_ASSET_DIR.resolve() or not path.is_file():
        return None
    return path


def list_icon_catalog(*, search: str | None = None, provider: str | None = None) -> list[IconInfo]:
    icons = list(discover_builtin_icons())
    if not icons:
        raise RuntimeError(
            "Listing icons requires the 'diagrams' package. "
            "Install the render extra first: uv sync --extra render"
        )
    icons.append(
        IconInfo(
            name="custom.supabase.Supabase",
            path=f"{ASSET_ICON_PREFIX}supabase.png",
            provider="custom",
            category="supabase",
        )
    )

    if provider:
        provider_key = provider.casefold()
        icons = [icon for icon in icons if icon.provider.casefold() == provider_key]
    if search:
        search_key = normalize_icon_key(search)
        icons = [icon for icon in icons if search_key in normalize_icon_key(icon.name)]
    return sorted(icons, key=lambda icon: (icon.name.casefold(), icon.name))
