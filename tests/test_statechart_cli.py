from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_diagrams.cli import build_composite_parser, run_statechart_mode


def test_statechart_parser():
    args = build_composite_parser().parse_args(
        ["statechart", "--spec", "workflow.tla", "--config", "workflow.cfg", "--render", "png"]
    )
    assert args.command == "statechart"
    assert args.spec == "workflow.tla"
    assert args.config == "workflow.cfg"
    assert args.render == "png"


def test_statechart_preserves_rule_violation_and_renders_chart(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "flow.tla"
    spec.write_text("---- MODULE flow ----\n====\n")
    output = tmp_path / "state-output"
    calls = []

    def fake_run(cmd, *, check):
        calls.append(cmd)
        if len(calls) == 1:
            output.mkdir()
            (output / "chart.mmd").write_text("stateDiagram-v2\n A --> B\n")
            (output / "report.md").write_text("Model only")
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("agent_diagrams.cli.subprocess.run", fake_run)
    args = build_composite_parser().parse_args(
        ["statechart", "--spec", str(spec), "--out", str(output), "--render", "png"]
    )
    assert run_statechart_mode(args) == 1
    assert calls[0][0] == "bash"
    assert calls[0][2] == str(spec)
    assert calls[1][0] == "bash"
    assert calls[1][2] == "--png"
    assert "TLC verdict exit code: 1" in capsys.readouterr().out


def test_statechart_checker_failure_does_not_render(tmp_path, monkeypatch):
    spec = tmp_path / "flow.tla"
    spec.write_text("dummy")
    calls = []
    def fail(cmd, *, check):
        calls.append(cmd)
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr("agent_diagrams.cli.subprocess.run", fail)
    args = build_composite_parser().parse_args(["statechart", "--spec", str(spec), "--render", "svg"])
    assert run_statechart_mode(args) == 2
    assert len(calls) == 1


def test_statechart_missing_spec_is_actionable(tmp_path):
    args = build_composite_parser().parse_args(
        ["statechart", "--spec", str(tmp_path / "missing.tla")]
    )
    with pytest.raises(FileNotFoundError, match="TLA\\+ specification missing"):
        run_statechart_mode(args)


def test_statechart_render_error_is_not_success(tmp_path, monkeypatch):
    spec = tmp_path / "ok.tla"
    spec.write_text("dummy")
    output = tmp_path / "checked"
    calls = []

    def fake_run(cmd, *, check):
        calls.append(cmd)
        if len(calls) == 1:
            output.mkdir()
            (output / "chart.mmd").write_text("stateDiagram-v2\nA --> B")
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr("agent_diagrams.cli.subprocess.run", fake_run)
    args = build_composite_parser().parse_args(
        ["statechart", "--spec", str(spec), "--out", str(output), "--render", "svg"]
    )
    assert run_statechart_mode(args) == 2
