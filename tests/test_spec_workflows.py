from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_diagrams.spec_workflows import (
    compare_specs,
    load_data_file,
    normalize_state_spec,
    validate_spec,
    write_compare_summary,
)

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


# ── load_data_file ──


def test_load_data_file_json(tmp_path):
    f = tmp_path / "spec.json"
    f.write_text(json.dumps({"nodes": [], "edges": []}))
    data = load_data_file(f)
    assert data == {"nodes": [], "edges": []}


def test_load_data_file_yaml(tmp_path):
    f = tmp_path / "spec.yaml"
    f.write_text(yaml.safe_dump({"title": "Test", "nodes": []}))
    data = load_data_file(f)
    assert data["title"] == "Test"


def test_load_data_file_json_fallback_yaml(tmp_path):
    f = tmp_path / "spec.json"
    f.write_text("title: Works\nnodes: []")  # YAML content in .json file
    data = load_data_file(f)
    assert data["title"] == "Works"


def test_load_data_file_non_dict_raises(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(ValueError, match="object"):
        load_data_file(f)


# ── normalize_state_spec ──


def test_normalize_no_states(sample_spec):
    result = normalize_state_spec(sample_spec)
    assert result is sample_spec


def test_normalize_with_named_state(multi_state_spec):
    result = normalize_state_spec(multi_state_spec, state="future")
    assert len(result["nodes"]) == 3
    assert result["title"] == "Migration"  # top-level key preserved


def test_normalize_default_to_current(multi_state_spec):
    result = normalize_state_spec(multi_state_spec)
    assert len(result["nodes"]) == 2  # current has 2 nodes


def test_normalize_missing_state_raises(multi_state_spec):
    with pytest.raises(ValueError, match="not found"):
        normalize_state_spec(multi_state_spec, state="nonexistent")


def test_normalize_state_requested_but_no_section(sample_spec):
    with pytest.raises(ValueError, match="no 'states' section"):
        normalize_state_spec(sample_spec, state="current")


# ── validate_spec ──


def test_validate_spec_valid(sample_spec):
    validate_spec(sample_spec)  # should not raise


def test_validate_spec_duplicate_node_id():
    spec = {
        "nodes": [
            {"id": "a", "label": "A"},
            {"id": "a", "label": "B"},
        ],
        "edges": [],
    }
    with pytest.raises(ValueError, match="Duplicate"):
        validate_spec(spec)


def test_validate_spec_edge_unknown_node():
    spec = {
        "nodes": [{"id": "a", "label": "A"}],
        "edges": [{"from": "a", "to": "missing"}],
    }
    with pytest.raises(ValueError, match="unknown nodes"):
        validate_spec(spec)


def test_validate_spec_node_unknown_cluster():
    spec = {
        "nodes": [{"id": "a", "label": "A", "cluster": "ghost"}],
        "edges": [],
        "clusters": [],
    }
    with pytest.raises(ValueError, match="unknown cluster"):
        validate_spec(spec)


def test_validate_spec_missing_node_id():
    spec = {"nodes": [{"label": "No ID"}], "edges": []}
    with pytest.raises(ValueError, match="must include 'id'"):
        validate_spec(spec)


def test_validate_spec_cluster_without_id():
    spec = {"nodes": [], "edges": [], "clusters": [{"label": "No ID"}]}
    with pytest.raises(ValueError, match="must include 'id'"):
        validate_spec(spec)


# ── compare_specs ──


def test_compare_identical(sample_spec):
    summary = compare_specs(sample_spec, sample_spec)
    assert summary["nodes_added"] == []
    assert summary["nodes_removed"] == []
    assert summary["edges_added"] == []
    assert summary["edges_removed"] == []


def test_compare_added_nodes(multi_state_spec):
    current = normalize_state_spec(multi_state_spec, state="current")
    future = normalize_state_spec(multi_state_spec, state="future")
    summary = compare_specs(current, future)
    assert "cache" in summary["nodes_added"]


def test_compare_removed_edges(multi_state_spec):
    current = normalize_state_spec(multi_state_spec, state="current")
    future = normalize_state_spec(multi_state_spec, state="future")
    summary = compare_specs(current, future)
    # current has web->db (SQL), future replaces it with web->cache, cache->db
    assert any("web" in e and "db" in e for e in summary["edges_removed"])


def test_compare_snapshot(multi_state_spec):
    current = normalize_state_spec(multi_state_spec, state="current")
    future = normalize_state_spec(multi_state_spec, state="future")
    summary = compare_specs(current, future)
    actual = json.dumps(summary, indent=2, sort_keys=True)
    golden_path = SNAPSHOTS_DIR / "compare_diff.json"
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual)
    golden = golden_path.read_text()
    assert actual == golden, "Compare diff output diverged from golden snapshot"


# ── write_compare_summary ──


def test_write_compare_summary_format(tmp_path):
    summary = {
        "nodes_added": ["cache"],
        "nodes_removed": [],
        "edges_added": ["web -> cache (get/set)"],
        "edges_removed": ["web -> db (SQL)"],
    }
    out = tmp_path / "diff.md"
    write_compare_summary(summary, out)
    content = out.read_text()
    assert "# Architecture Diff" in content
    assert "## Nodes Added" in content
    assert "- cache" in content
    assert "## Nodes Removed" in content
    assert "- None" in content
