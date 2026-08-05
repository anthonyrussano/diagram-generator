from __future__ import annotations

import importlib
import shutil

import pytest

from agent_diagrams.icon_catalog import (
    ICON_ALIASES,
    list_icon_catalog,
    normalize_icon_key,
    resolve_asset_path,
    resolve_node_icon,
    resolve_spec_icon,
)
from agent_diagrams.model import GraphData, Node
from agent_diagrams.renderers.diagrams_renderer import unresolved_icon_nodes
from agent_diagrams.spec_workflows import render_spec_diagram


def require_real_diagrams_package():
    diagrams = pytest.importorskip("diagrams")
    if not hasattr(diagrams, "__path__"):
        pytest.skip("the real diagrams package is not installed")


def test_normalize_icon_key_handles_language_punctuation():
    assert normalize_icon_key("C++") == "cplusplus"
    assert normalize_icon_key("C#") == "csharp"
    assert normalize_icon_key("Next.js") == "next.js"


@pytest.mark.parametrize(
    ("kind", "label", "expected"),
    [
        ("cloudflare.dns", "Cloudflare DNS", "diagrams.saas.cdn.Cloudflare"),
        ("tf.cloudflare_record", "www", "diagrams.saas.cdn.Cloudflare"),
        ("supabase.database", "Application DB", "asset:supabase.png"),
        ("tf.supabase_project", "backend", "asset:supabase.png"),
        ("json.file", "worker.py", "diagrams.programming.language.Python"),
        ("json.file", "frontend.tsx", "diagrams.programming.framework.React"),
        ("tool", "GitHub Actions", "diagrams.onprem.ci.GithubActions"),
        ("local.host", "Local host", "diagrams.onprem.compute.Server"),
        ("local.network_interface.ethernet", "eth0", "asset:network-interface.png"),
        ("local.network_interface.loopback", "lo", "asset:network-interface.png"),
        ("local.ip_address.ipv4", "10.0.0.1/24", "diagrams.generic.network.Subnet"),
        ("local.ip_address.ipv6", "fe80::1/64", "diagrams.generic.network.Subnet"),
        ("local.gateway", "10.0.0.1", "diagrams.generic.network.Router"),
    ],
)
def test_resolve_common_devops_icons(kind, label, expected):
    assert resolve_node_icon(kind, label, "node") == expected


@pytest.mark.parametrize(
    ("kind", "label", "node_id"),
    [
        ("component", "user-service", "user-service"),
        ("component", "users-service", "users-service"),
        ("component", "auth-service", "auth-service"),
        ("component", "customer-service", "customer-service"),
        ("component", "deployment-pipeline", "deployment-pipeline"),
    ],
)
def test_generic_infra_nouns_do_not_win_a_guess_from_an_unrelated_label(kind, label, node_id):
    # None of these labels carry real evidence of a specific technology or
    # Kubernetes resource; a wrong guess (a person icon, an assumed vendor
    # brand, an arbitrary Kubernetes Service/Deployment) is worse than being
    # reported as an unresolved icon fallback.
    assert resolve_node_icon(kind, label, node_id) is None


@pytest.mark.parametrize(
    ("kind", "label", "expected"),
    [
        ("tf.aws_security_group", "web-sg", "diagrams.generic.network.Firewall"),
        ("tf.aws_iam_role", "app-role", "diagrams.aws.security.IAMRole"),
        ("tf.aws_iam_policy", "app-policy", "diagrams.aws.security.IAMPermissions"),
    ],
)
def test_structured_terraform_kinds_get_explicit_provider_aware_icons(kind, label, expected):
    # These would otherwise fall through to the dynamic catalog's per-token
    # short-name matching and pick up an arbitrary, wrong-provider icon (e.g.
    # a Kubernetes RBAC "Role" or an Azure "Policy" for an AWS resource).
    assert resolve_node_icon(kind, label, "node") == expected


def test_exact_generic_kind_still_resolves_to_its_dedicated_icon():
    assert resolve_node_icon("user", "A user", "u1") == "diagrams.onprem.client.User"
    assert resolve_node_icon("aws.iam", "IAM role", "role") == "diagrams.aws.security.IAM"
    assert resolve_node_icon("gcp", "Google Cloud", "n") == "diagrams.gcp.compute.ComputeEngine"
    assert resolve_node_icon("kubernetes", "K8s", "n") == "diagrams.k8s.compute.Pod"
    assert resolve_node_icon("node", "Node runtime", "n1") == "diagrams.programming.language.NodeJS"


def test_dynamic_catalog_short_names_do_not_leak_into_token_fallback():
    # "gcp"/"k8s" are broad platform names mapped to one representative
    # sub-icon (Compute Engine / Pod); a structured Terraform resource type
    # under that platform must not inherit that unrelated sub-icon just
    # because the platform name appears in it.
    assert resolve_node_icon("tf.gcp_iam_policy", "reader-policy", "n") is None
    assert resolve_node_icon("tf.k8s_secret_resource", "app-secret", "n") is None
    # "Role"/"Policy" happen to be unique to exactly one unrelated provider
    # (k8s.rbac / azure.managementgovernance) purely by chance of what ships
    # in the installed diagrams package; the dynamically discovered catalog
    # must not be consulted for per-token fallback at all.
    assert resolve_node_icon("tf.azurerm_role_assignment", "role-assignment", "n") is None
    assert resolve_node_icon("tf.aws_kms_key", "app-key", "n") is None


@pytest.mark.parametrize(
    ("kind", "label", "node_id"),
    [
        ("component", "Role", "n1"),
        ("component", "Policy", "n2"),
        ("component", "node-1", "node-1"),
        ("component", "node-service", "node-service"),
        ("component", "api-node", "api-node"),
    ],
)
def test_dynamic_short_names_do_not_leak_into_inferred_kind_or_label(kind, label, node_id):
    # "Role"/"Policy" are unqualified dynamic-catalog short names (unique to
    # one unrelated provider by accident), and "node" is this project's own
    # generic term for a graph entity. None of these should win an icon guess
    # from a bare kind, label, or node id — only an explicit attrs.icon (or a
    # provider-qualified name) may draw on them.
    assert resolve_node_icon(kind, label, node_id) is None


def test_dynamic_short_names_remain_available_for_explicit_icon_selection():
    assert resolve_node_icon("x", "x", "x", explicit_icon="Role") == "diagrams.k8s.rbac.Role"
    assert resolve_node_icon("x", "x", "x", explicit_icon="Policy") == "diagrams.azure.managementgovernance.Policy"
    assert resolve_spec_icon("Role") == "diagrams.k8s.rbac.Role"


def test_explicit_node_icon_takes_precedence():
    assert resolve_node_icon(
        "aws.ec2",
        "Compute",
        "node",
        explicit_icon="supabase",
    ) == "asset:supabase.png"


def test_unknown_explicit_icon_is_not_silently_substituted():
    assert resolve_node_icon(
        "aws.ec2",
        "Compute",
        "node",
        explicit_icon="vendor.icon-that-does-not-exist",
    ) is None

    assert resolve_spec_icon("diagrams.vendor.missing.Icon") is None


def test_supabase_asset_is_bundled():
    path = resolve_asset_path(resolve_spec_icon("supabase"))
    assert path is not None
    assert path.name == "supabase.png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_network_interface_asset_is_bundled():
    path = resolve_asset_path(resolve_spec_icon("custom.local.NetworkInterface"))
    assert path is not None
    assert path.name == "network-interface.png"
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    ("icon", "expected"),
    [
        ("custom.supabase.Supabase", "asset:supabase.png"),
        ("asset:supabase.png", "asset:supabase.png"),
        ("custom.local.NetworkInterface", "asset:network-interface.png"),
        ("asset:network-interface.png", "asset:network-interface.png"),
    ],
)
def test_bundled_catalog_references_are_resolvable(icon, expected):
    assert resolve_spec_icon(icon) == expected


@pytest.mark.parametrize(
    ("icon", "label"),
    [
        ("supabase", "Supabase"),
        ("custom.local.NetworkInterface", "eth0"),
    ],
)
def test_custom_icon_is_embedded_in_rendered_svg(tmp_path, icon, label):
    require_real_diagrams_package()
    if shutil.which("dot") is None:
        pytest.skip("Graphviz is not installed")

    output = render_spec_diagram(
        {
            "nodes": [{"id": "custom", "label": label, "icon": icon}],
            "edges": [],
        },
        tmp_path / "custom-icon",
        output_format="svg",
    )

    rendered = output.read_text(encoding="utf-8")
    assert label in rendered
    assert "data:image/png;base64" in rendered


def test_unknown_icons_are_reported_deterministically():
    graph = GraphData(
        nodes=[
            Node(id="z", label="Unknown Z", kind="vendor.unknown-z", source="test"),
            Node(id="a", label="Unknown A", kind="vendor.unknown-a", source="test"),
        ]
    )
    assert [item["id"] for item in unresolved_icon_nodes(graph)] == ["a", "z"]


def test_dynamic_catalog_exposes_diagrams_icons():
    require_real_diagrams_package()
    icons = list_icon_catalog()
    names = {icon.name for icon in icons}

    assert len(icons) >= 2000
    assert "programming.language.Python" in names
    assert "saas.cdn.Cloudflare" in names
    assert "custom.supabase.Supabase" in names
    assert "custom.local.NetworkInterface" in names
    assert [icon.name.casefold() for icon in icons] == sorted(icon.name.casefold() for icon in icons)


def test_all_builtin_alias_targets_are_importable():
    require_real_diagrams_package()
    for icon_ref in ICON_ALIASES.values():
        if icon_ref.startswith("asset:"):
            assert resolve_asset_path(icon_ref) is not None
            continue
        module_name, class_name = icon_ref.rsplit(".", 1)
        assert getattr(importlib.import_module(module_name), class_name)


@pytest.mark.parametrize(
    "canonical_name",
    [
        "programming.language.Python",
        "saas.cdn.Cloudflare",
        "onprem.container.Docker",
        "gcp.compute.ComputeEngine",
        "azure.compute.VirtualMachine",
    ],
)
def test_canonical_catalog_paths_are_importable(canonical_name):
    require_real_diagrams_package()
    icon_ref = resolve_spec_icon(canonical_name)
    assert icon_ref is not None
    module_name, class_name = icon_ref.rsplit(".", 1)
    assert getattr(importlib.import_module(module_name), class_name)
