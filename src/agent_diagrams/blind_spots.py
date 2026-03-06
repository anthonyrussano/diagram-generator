from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def collect_blind_spots(
    *,
    errors: list[str] | None = None,
    empty_sources: list[str] | None = None,
    unqueryable_resources: list[str] | None = None,
    permission_denials: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured blind spots report."""
    return {
        "errors": errors or [],
        "empty_sources": empty_sources or [],
        "unqueryable_resources": unqueryable_resources or [],
        "permission_denials": permission_denials or [],
        "has_blind_spots": bool(
            errors or empty_sources or unqueryable_resources or permission_denials
        ),
    }


def write_blind_spots_json(report: dict[str, Any], path: Path) -> Path:
    """Write blind spots report as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_blind_spots_md(report: dict[str, Any], path: Path) -> Path:
    """Write blind spots report as Markdown."""
    sections = [
        ("errors", "Collection Errors"),
        ("empty_sources", "Empty Sources"),
        ("unqueryable_resources", "Unqueryable Resources"),
        ("permission_denials", "Permission Denials"),
    ]

    lines = ["# Blind Spots Report", ""]
    for key, title in sections:
        items = report.get(key, [])
        lines.append(f"## {title}")
        if not items:
            lines.append("- None")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
