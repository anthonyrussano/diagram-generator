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
    ],
)
def test_resolve_common_devops_icons(kind, label, expected):
    assert resolve_node_icon(kind, label, "node") == expected


@pytest.mark.parametrize(
    ("kind", "label", "node_id", "expected"),
    [
        ("component", "user-service", "user-service", "diagrams.k8s.network.Service"),
        ("component", "users-service", "users-service", "diagrams.k8s.network.Service"),
        ("component", "auth-service", "auth-service", "diagrams.k8s.network.Service"),
        ("tf.aws_security_group", "web-sg", "sg-123", "diagrams.generic.network.Firewall"),
    ],
)
def test_generic_person_and_vendor_words_do_not_win_over_other_tokens(kind, label, node_id, expected):
    assert resolve_node_icon(kind, label, node_id) == expected


def test_exact_generic_kind_still_resolves_to_its_dedicated_icon():
    assert resolve_node_icon("user", "A user", "u1") == "diagrams.onprem.client.User"
    assert resolve_node_icon("aws.iam", "IAM role", "role") == "diagrams.aws.security.IAM"


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


@pytest.mark.parametrize("icon", ["custom.supabase.Supabase", "asset:supabase.png"])
def test_supabase_catalog_references_are_resolvable(icon):
    assert resolve_spec_icon(icon) == "asset:supabase.png"


def test_custom_icon_is_embedded_in_rendered_svg(tmp_path):
    require_real_diagrams_package()
    if shutil.which("dot") is None:
        pytest.skip("Graphviz is not installed")

    output = render_spec_diagram(
        {
            "nodes": [{"id": "database", "label": "Supabase", "icon": "supabase"}],
            "edges": [],
        },
        tmp_path / "supabase",
        output_format="svg",
    )

    rendered = output.read_text(encoding="utf-8")
    assert "Supabase" in rendered
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
