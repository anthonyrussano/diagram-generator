from __future__ import annotations

import json
from pathlib import Path

from agent_diagrams.blind_spots import (
    collect_blind_spots,
    write_blind_spots_json,
    write_blind_spots_md,
)

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def test_collect_blind_spots_empty():
    report = collect_blind_spots()
    assert report["has_blind_spots"] is False
    assert report["errors"] == []
    assert report["empty_sources"] == []


def test_collect_blind_spots_with_errors():
    report = collect_blind_spots(errors=["aws: AccessDenied"])
    assert report["has_blind_spots"] is True
    assert report["errors"] == ["aws: AccessDenied"]


def test_collect_blind_spots_multiple():
    report = collect_blind_spots(
        errors=["err1"],
        empty_sources=["terraform: no resources found"],
        permission_denials=["aws:rds denied"],
    )
    assert report["has_blind_spots"] is True
    assert len(report["errors"]) == 1
    assert len(report["empty_sources"]) == 1
    assert len(report["permission_denials"]) == 1


def test_write_blind_spots_json(tmp_path):
    report = collect_blind_spots(errors=["fail"])
    out = tmp_path / "bs.json"
    write_blind_spots_json(report, out)
    data = json.loads(out.read_text())
    assert data["has_blind_spots"] is True
    assert data["errors"] == ["fail"]


def test_write_blind_spots_md(tmp_path):
    report = collect_blind_spots(
        errors=["aws: no creds"],
        empty_sources=["terraform: empty"],
    )
    out = tmp_path / "bs.md"
    write_blind_spots_md(report, out)
    content = out.read_text()
    assert "# Blind Spots Report" in content
    assert "## Collection Errors" in content
    assert "- aws: no creds" in content
    assert "## Empty Sources" in content
    assert "- terraform: empty" in content
    assert "## Unqueryable Resources" in content
    assert "- None" in content


def test_write_blind_spots_md_snapshot(tmp_path):
    report = collect_blind_spots(
        errors=["aws: AccessDenied"],
        empty_sources=["terraform: no resources found"],
    )
    out = tmp_path / "bs.md"
    write_blind_spots_md(report, out)
    actual = out.read_text()
    golden_path = SNAPSHOTS_DIR / "blind_spots.md"
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual)
    golden = golden_path.read_text()
    assert actual == golden, "Blind spots MD output diverged from golden snapshot"
