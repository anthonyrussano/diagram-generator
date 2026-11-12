from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_diagrams import cli
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


def test_statechart_runtime_includes_wrappers_engine_and_attribution():
    runtime = cli._statechart_root()
    for relative in (
        "scripts/statechart",
        "scripts/bootstrap.sh",
        "scripts/render",
        "scripts/render.mjs",
        "scripts/screenshot.cjs",
        "vendor/statechart/scripts/statechart",
        "vendor/statechart/scripts/statechart.ts",
        "vendor/statechart/references/render.md",
        "vendor/statechart/LICENSE",
        "vendor/statechart/UPSTREAM",
        "package.json",
        "package-lock.json",
        "examples/group-provisioning/GroupProvisioning.tla",
    ):
        assert (runtime / relative).is_file(), relative


def test_statechart_missing_spec_process_exits_with_tool_error(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", "-m", "agent_diagrams.cli", "statechart",
         "--spec", str(tmp_path / "missing.tla")],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    assert "TLA+ specification missing:" in result.stderr
    assert not list(tmp_path.glob("*-chart"))


def test_statechart_process_reaches_runtime_without_optional_dependencies(tmp_path):
    spec = tmp_path / "flow.tla"
    spec.write_text("---- MODULE flow ----\n====\n")
    result = subprocess.run(
        [sys.executable, "-I", "-m", "agent_diagrams.cli", "statechart", "--spec", str(spec)],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
        env={**os.environ, "JAVA": str(tmp_path / "missing-java"),
             "TLA2TOOLS": str(tmp_path / "missing-tla2tools.jar")},
    )
    assert result.returncode == 2
    assert "Java or TLC is missing." in result.stderr
    assert "scripts/bootstrap.sh" in result.stderr
    assert not list(tmp_path.glob("*-chart"))


@pytest.mark.parametrize("verdict", [0, 1])
def test_statechart_main_preserves_checker_verdict(tmp_path, monkeypatch, verdict):
    spec = tmp_path / "flow.tla"
    spec.write_text("dummy")
    monkeypatch.setattr(sys, "argv", ["diagram-gen", "statechart", "--spec", str(spec)])
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=verdict))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == verdict


def test_statechart_missing_runtime_exits_with_tool_error(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "flow.tla"
    spec.write_text("dummy")
    monkeypatch.setattr(sys, "argv", ["diagram-gen", "statechart", "--spec", str(spec)])
    monkeypatch.setattr(cli, "_statechart_root", lambda: tmp_path / "missing-runtime")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "Statechart runtime missing:" in capsys.readouterr().err


def test_statechart_execution_error_exits_with_tool_error(tmp_path, monkeypatch, capsys):
    spec = tmp_path / "flow.tla"
    spec.write_text("dummy")
    monkeypatch.setattr(sys, "argv", ["diagram-gen", "statechart", "--spec", str(spec)])

    def denied(*args, **kwargs):
        raise PermissionError("checker execution denied")

    monkeypatch.setattr(cli.subprocess, "run", denied)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "checker execution denied" in capsys.readouterr().err
