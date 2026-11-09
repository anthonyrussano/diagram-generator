from __future__ import annotations

from pathlib import Path

import pytest

from agent_diagrams.cli import (
    _apply_review_bundle,
    build_composite_parser,
    build_parser,
    run_mermaid_mode,
)


def test_review_bundle_enables_editable_scene_previews_and_zip():
    args = build_parser().parse_args(["--review-bundle", "--diagram-format", "pdf"])
    _apply_review_bundle(args)
    assert args.diagram_format == ["pdf", "svg", "png", "drawio"]
    assert args.artifact_folder is True
    assert args.zip_artifacts is True
    assert args.svg is False  # Graphviz previews match the editable draw.io layout.
    assert args.png is False


def test_review_bundle_does_not_change_default_outputs():
    args = build_parser().parse_args([])
    _apply_review_bundle(args)
    assert args.diagram_format is None
    assert args.artifact_folder is False
    assert args.zip_artifacts is False


def test_mermaid_parser_defaults_to_source_and_both_images():
    args = build_composite_parser().parse_args(["mermaid", "--input", "flow.mmd"])
    assert args.command == "mermaid"
    assert args.format is None
    assert args.mermaid_runtime == "auto"
    assert args.out_dir == "output"


def test_mermaid_fenced_markdown_publishes_source_and_images(tmp_path, monkeypatch, capsys):
    src = tmp_path / "article.md"
    src.write_text("# Diagram\n\n```mermaid\nflowchart LR\n  a --> b\n```\n", encoding="utf-8")
    output_dir = tmp_path / "rendered"
    calls = []

    def fake_render(source: Path, output: Path, **kwargs):
        assert source.parent == output.parent
        assert source.read_text(encoding="utf-8") == "flowchart LR\n  a --> b\n"
        calls.append((output.suffix, kwargs["runtime"]))
        output.write_bytes(b"rendered")
        return output

    monkeypatch.setattr("agent_diagrams.cli.render_mermaid_image", fake_render)
    args = build_composite_parser().parse_args(
        ["mermaid", "--input", str(src), "--out-dir", str(output_dir), "--output", "deployment"]
    )
    run_mermaid_mode(args)

    assert calls == [(".svg", "auto"), (".png", "auto")]
    assert (output_dir / "deployment.mmd").read_text() == "flowchart LR\n  a --> b\n"
    assert (output_dir / "deployment.svg").read_bytes() == b"rendered"
    assert (output_dir / "deployment.png").read_bytes() == b"rendered"
    assert len(list(output_dir.glob(".diagram-gen-*"))) == 0
    assert "deployment.png" in capsys.readouterr().out


def test_mermaid_render_failure_does_not_publish_partial_artifacts(tmp_path, monkeypatch):
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart LR\n  a --> b\n", encoding="utf-8")
    out_dir = tmp_path / "output"

    def fail_render(source_path: Path, output_path: Path, **kwargs):
        if output_path.suffix == ".svg":
            output_path.write_text("<svg/>")
            return output_path
        raise RuntimeError("invalid mermaid syntax")

    monkeypatch.setattr("agent_diagrams.cli.render_mermaid_image", fail_render)
    args = build_composite_parser().parse_args(
        ["mermaid", "--input", str(source), "--out-dir", str(out_dir)]
    )
    with pytest.raises(RuntimeError, match="invalid mermaid syntax"):
        run_mermaid_mode(args)

    assert not list(out_dir.glob("*.mmd"))
    assert not list(out_dir.glob("*.svg"))
    assert not list(out_dir.glob("*.png"))
    assert not list(out_dir.glob(".diagram-gen-*"))


def test_mermaid_missing_input_fails_before_render(tmp_path):
    args = build_composite_parser().parse_args(
        ["mermaid", "--input", str(tmp_path / "missing.mmd")]
    )
    with pytest.raises(FileNotFoundError, match="Mermaid input not found"):
        run_mermaid_mode(args)


def test_mermaid_empty_input_fails_before_render(tmp_path):
    source = tmp_path / "empty.mmd"
    source.write_text("  \n", encoding="utf-8")
    args = build_composite_parser().parse_args(["mermaid", "--input", str(source)])
    with pytest.raises(ValueError, match="Mermaid source is empty"):
        run_mermaid_mode(args)
