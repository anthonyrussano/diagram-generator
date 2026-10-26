from __future__ import annotations

import json

from agent_diagrams.collectors import collect_from_terraform, discover_files


def test_hcl_cross_file_references_and_explicit_dependencies(tmp_path):
    (tmp_path / "network.tf").write_text(
        'resource "aws_vpc" "main" { cidr_block = "10.0.0.0/16" }'
    )
    (tmp_path / "main.tf").write_text("""
data "aws_ami" "linux" { most_recent = true }
resource "aws_instance" "web" {
  ami = data.aws_ami.linux.id
  vpc_id = aws_vpc.main.id
  depends_on = [aws_vpc.main]
  tags = { description = "aws_instance.not_a_reference" }
}
""")
    graph = collect_from_terraform([tmp_path])
    assert {node.id for node in graph.nodes} == {
        "tf:aws_vpc.main",
        "tf:data.aws_ami.linux",
        "tf:aws_instance.web",
    }
    assert {(edge.src, edge.dst, edge.rel) for edge in graph.edges} == {
        ("tf:aws_instance.web", "tf:aws_vpc.main", "references"),
        ("tf:aws_instance.web", "tf:aws_vpc.main", "depends_on"),
        ("tf:aws_instance.web", "tf:data.aws_ami.linux", "references"),
    }
    assert not graph.metadata["warnings"]


def test_hcl_indices_functions_templates_and_literal_strings(tmp_path):
    path = tmp_path / "main.tf"
    path.write_text("""
resource "aws_subnet" "private" { count = 2 }
resource "aws_instance" "literal" {}
resource "aws_instance" "web" {
  subnet_id = aws_subnet.private[0].id
  name = "prefix-${aws_subnet.private[1].id}"
  other = format("aws_instance.literal.id", aws_subnet.private[0].id)
  escaped = "$${aws_instance.literal.id}"
  plain = "aws_instance.literal.id"
}
""")
    graph = collect_from_terraform([path])
    assert {(edge.dst, edge.rel) for edge in graph.edges} == {
        ("tf:aws_subnet.private", "references")
    }


def test_module_calls_unresolved_and_invalid_files_are_reported(tmp_path):
    (tmp_path / "main.tf").write_text("""
module "network" { source = "./network" }
resource "aws_instance" "web" {
  subnet_id = module.network.subnet_id
  depends_on = [aws_vpc.missing]
}
""")
    (tmp_path / "broken.tf").write_text('resource "incomplete" {')
    graph = collect_from_terraform([tmp_path])
    assert {node.id for node in graph.nodes} == {
        "tf:module.network",
        "tf:aws_instance.web",
    }
    assert [(edge.dst, edge.rel) for edge in graph.edges] == [
        ("tf:module.network", "references")
    ]
    assert any("aws_vpc.missing" in warning for warning in graph.metadata["warnings"])
    assert any("broken.tf" in warning for warning in graph.metadata["warnings"])
    assert any("not expanded" in warning for warning in graph.metadata["warnings"])


def test_state_module_addresses_and_dependencies(tmp_path):
    path = tmp_path / "main.tfstate"
    path.write_text(
        json.dumps(
            {
                "resources": [
                    {
                        "module": "module.app",
                        "type": "aws_vpc",
                        "name": "main",
                        "instances": [],
                    },
                    {
                        "module": "module.app",
                        "type": "aws_instance",
                        "name": "web",
                        "instances": [{"dependencies": ["module.app.aws_vpc.main"]}],
                    },
                    {"mode": "data", "type": "aws_ami", "name": "linux"},
                ]
            }
        )
    )
    graph = collect_from_terraform([path])
    assert "tf:data.aws_ami.linux" in {node.id for node in graph.nodes}
    assert [(edge.src, edge.dst) for edge in graph.edges] == [
        ("tf:module.app.aws_instance.web", "tf:module.app.aws_vpc.main")
    ]


def test_separate_module_directories_do_not_merge(tmp_path):
    for directory in ("prod", "dev"):
        folder = tmp_path / directory
        folder.mkdir()
        (folder / "main.tf").write_text('resource "aws_instance" "web" {}')
    graph = collect_from_terraform([tmp_path / "prod", tmp_path / "dev"])
    assert {node.id for node in graph.nodes} == {
        "tf:prod:aws_instance.web",
        "tf:dev:aws_instance.web",
    }


def test_discovery_includes_hcl_and_excludes_terraform_cache(tmp_path):
    (tmp_path / "main.tf").touch()
    cache = tmp_path / ".terraform"
    cache.mkdir()
    (cache / "cached.tf").touch()
    assert discover_files(tmp_path)["tf"] == [tmp_path / "main.tf"]


def test_config_and_state_preserve_config_references(tmp_path):
    (tmp_path / "main.tf").write_text("""
resource "aws_vpc" "main" {}
resource "aws_instance" "web" { vpc_id = aws_vpc.main.id }
""")
    state = tmp_path / "main.tfstate"
    state.write_text(
        json.dumps({"resources": [{"type": "aws_instance", "name": "web"}]})
    )
    graph = collect_from_terraform([tmp_path / "main.tf", state])
    assert len(graph.nodes) == 2
    assert [(edge.src, edge.dst) for edge in graph.edges] == [
        ("tf:aws_instance.web", "tf:aws_vpc.main")
    ]


def test_numeric_expressions_are_not_resource_addresses(tmp_path):
    path = tmp_path / "main.tf"
    path.write_text('resource "example_resource" "main" { value = 1.25 + 2.5 }')
    graph = collect_from_terraform([path])
    assert len(graph.nodes) == 1
    assert not graph.edges
    assert not graph.metadata["warnings"]
