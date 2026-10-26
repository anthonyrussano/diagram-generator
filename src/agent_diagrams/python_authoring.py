"""Execute trusted Diagrams scripts in a dedicated, timeout-controlled process."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import runpy
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

FORMATS = ("png", "svg", "pdf", "dot", "drawio")


def render_python_script(
    script: Path, output_prefix: Path, *, formats: list[str], timeout: int = 90
) -> dict:
    script, output_prefix = script.resolve(), output_prefix.resolve()
    if not script.is_file():
        raise ValueError(f"Python diagram script does not exist: {script}")
    if timeout < 1:
        raise ValueError("Python authoring timeout must be at least 1 second.")
    if not formats or any(fmt not in FORMATS for fmt in formats):
        raise ValueError(
            f"Python authoring formats must be selected from {', '.join(FORMATS)}."
        )
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="diagram-gen-python-") as temporary:
        report = Path(temporary) / "report.json"
        command = [
            sys.executable,
            "-m",
            "agent_diagrams.python_authoring",
            str(script),
            str(output_prefix),
            str(report),
            *dict.fromkeys(formats),
        ]
        # Module execution also works from an editable checkout when called by
        # a parent that imported src via PYTHONPATH/pytest's pythonpath setting.
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            dict.fromkeys([str(Path(__file__).resolve().parents[1]), *sys.path])
        )
        process = subprocess.Popen(
            command,
            cwd=script.parent,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            # Kill Graphviz and any other descendants as well as the script.
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise RuntimeError(
                f"Python diagram generation timed out after {timeout} seconds: {script}"
            ) from exc
        if process.returncode:
            raise RuntimeError(
                f"Python diagram script failed (exit {process.returncode}): {script}\n{stderr or stdout}"
            )
        if not report.is_file():
            raise RuntimeError(
                f"Python diagram script did not produce a completion report: {script}"
            )
        result = json.loads(report.read_text())
        if not result["diagrams"]:
            raise ValueError("Python script did not create any Diagram contexts.")
        result["stdout"] = stdout
        return result


def _run(script: Path, output_prefix: Path, report: Path, formats: list[str]) -> None:
    from diagrams import Diagram

    from .renderers.diagrams_renderer import _inline_svg_image_refs
    from .renderers.drawio import export_dot_to_drawio

    diagrams: list[dict] = []
    original_init, original_render = Diagram.__init__, Diagram.render
    signature = inspect.signature(original_init)
    count = 0

    def initialize(self, *args, **kwargs):
        nonlocal count
        count += 1
        prefix = (
            output_prefix
            if count == 1
            else output_prefix.with_name(f"{output_prefix.name}-{count}")
        )
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        bound.arguments.update(
            filename=str(prefix),
            show=False,
            outformat=list(
                dict.fromkeys("dot" if fmt == "drawio" else fmt for fmt in formats)
            ),
        )
        original_init(*bound.args, **bound.kwargs)

    def render(self):
        original_render(self)
        paths = []
        for fmt in formats:
            path = Path(f"{self.filename}.{fmt}")
            if fmt == "drawio":
                export_dot_to_drawio(
                    Path(f"{self.filename}.dot"), path, asset_dir=script.parent
                )
            elif fmt == "svg":
                _inline_svg_image_refs(path)
            if not path.is_file():
                raise RuntimeError(
                    f"Python script failed to create expected artifact: {path}"
                )
            paths.append(str(path))
        # Parse the actual authored graph so counts include loops/helpers and
        # imported components, rather than counting Python source statements.
        result = subprocess.run(
            ["dot", "-Tdot_json"],
            input=self.dot.source,
            text=True,
            capture_output=True,
            check=True,
        )
        graph = json.loads(result.stdout)
        diagrams.append(
            {
                "name": self.name,
                "nodes": len(graph.get("objects", [])) - graph.get("_subgraph_cnt", 0),
                "edges": len(graph.get("edges", [])),
                "paths": paths,
            }
        )

    Diagram.__init__, Diagram.render = initialize, render
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script)]
    runpy.run_path(str(script), run_name="__main__")
    report.write_text(json.dumps({"diagrams": diagrams}), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("formats", nargs="+", choices=FORMATS)
    args = parser.parse_args()
    _run(args.script, args.output, args.report, args.formats)


if __name__ == "__main__":
    main()
