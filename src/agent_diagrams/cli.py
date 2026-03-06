from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .collectors import (
    collect_from_aws_cli,
    collect_from_helm_charts,
    collect_from_json,
    collect_from_kubernetes,
    collect_from_terraform,
    discover_files,
)
from .live_k8s import annotate_spec, generate_namespace_spec, summarize_namespace
from .model import GraphData
from .normalize import dedupe_graph
from .renderers.diagrams_renderer import render_with_diagrams
from .renderers.images import DEFAULT_IMAGE, render_mermaid_image
from .renderers.json_renderer import render_json
from .renderers.mermaid import render_mermaid
from .blind_spots import collect_blind_spots, write_blind_spots_json, write_blind_spots_md
from .spec_workflows import (
    compare_specs,
    load_data_file,
    normalize_state_spec,
    render_spec_diagram,
    write_compare_summary,
)

COMPOSITE_COMMANDS = {"spec", "compare", "k8s", "aws-boto3"}


def _merge_graphs(graphs: list[GraphData]) -> GraphData:
    merged = GraphData(metadata={"sources": [g.metadata for g in graphs]})
    for graph in graphs:
        merged.nodes.extend(graph.nodes)
        merged.edges.extend(graph.edges)
    return dedupe_graph(merged)


def _resolve_output_prefix(prefix: str, out_dir: str) -> Path:
    path = Path(prefix)
    if not path.is_absolute() and path.parent == Path("."):
        path = Path(out_dir) / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_output_file(filename: str, out_dir: str) -> Path:
    path = Path(filename)
    if not path.is_absolute() and path.parent == Path("."):
        path = Path(out_dir) / path.name
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_data_file(data: dict, path: Path) -> None:
    if path.suffix.lower() in {".yaml", ".yml"}:
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
        return
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate infrastructure diagrams from AWS, Terraform, JSON, and Kubernetes sources",
        epilog=(
            "Composite workflows are also available: diagram-gen spec --help, "
            "diagram-gen compare --help, diagram-gen k8s --help, diagram-gen aws-boto3 --help"
        ),
    )
    parser.add_argument("--source", action="append", choices=["aws", "terraform", "json", "kubernetes"], help="Explicit sources to scan")
    parser.add_argument("--discover", action="store_true", help="Auto-discover local json/tfstate/tf.json/k8s manifest files")
    parser.add_argument("--root", default=".", help="Root folder for discovery")
    parser.add_argument("--profile", default="default", help="AWS profile")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--json", nargs="*", default=[], help="Explicit JSON files")
    parser.add_argument("--terraform", nargs="*", default=[], help="Explicit Terraform files (.tfstate, .tf.json)")
    parser.add_argument("--k8s", nargs="*", default=[], help="Explicit Kubernetes manifest files")
    parser.add_argument("--helm-chart", nargs="*", default=[], help="Helm chart directories to render with 'helm template'")
    parser.add_argument("--helm-values", nargs="*", default=[], help="Optional Helm values files")
    parser.add_argument("--helm-namespace", default="default", help="Namespace to use for Helm template rendering")
    parser.add_argument("--helm-release-prefix", default="diagram", help="Release name prefix used for Helm template rendering")
    parser.add_argument("--live-k8s", action="store_true", help="Include live kubernetes resources via kubectl")
    parser.add_argument("--out-dir", default="output", help="Output directory")
    parser.add_argument("--name", default="infra", help="Output base name")
    parser.add_argument("--direction", default="LR", choices=["LR", "TB", "RL", "BT"], help="Diagram direction")
    parser.add_argument("--svg", action="store_true", help="Render Mermaid output to SVG using dockerized mermaid-cli")
    parser.add_argument("--png", action="store_true", help="Render Mermaid output to PNG using dockerized mermaid-cli")
    parser.add_argument("--mermaid-image", default=DEFAULT_IMAGE, help="Docker image for mermaid-cli")
    parser.add_argument("--mermaid-theme", default=None, help="Optional Mermaid theme (default/dark/forest/neutral)")
    parser.add_argument("--mermaid-background", default="transparent", help="Image background color (transparent/white/etc)")
    parser.add_argument(
        "--diagram-format",
        action="append",
        choices=["png", "svg", "pdf"],
        help="Optional non-Mermaid output format rendered with python-diagrams (repeat for multiple outputs)",
    )
    parser.add_argument("--diagram-title", default="Infrastructure Diagram", help="Title for non-Mermaid rendered diagram")
    parser.add_argument("--artifact-folder", action="store_true", help="Write outputs into out-dir/<name>/")
    parser.add_argument("--zip-artifacts", action="store_true", help="Zip all outputs into out-dir/<name>.zip")
    return parser


def build_composite_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Composite diagram workflows: spec rendering, current-vs-future comparison, "
            "and live Kubernetes discovery/annotation."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    spec_parser = commands.add_parser("spec", help="Render a diagram from a JSON/YAML spec")
    spec_parser.add_argument("--spec", required=True, help="Path to spec file")
    spec_parser.add_argument("--state", help="State name when spec contains a 'states' object")
    spec_parser.add_argument("--out-dir", default="output", help="Output directory for relative artifact paths")
    spec_parser.add_argument("--output", "-o", default="architecture", help="Output file prefix")
    spec_parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"], help="Output format")
    spec_parser.add_argument("--direction", choices=["TB", "LR", "BT", "RL"], help="Override diagram direction")
    spec_parser.set_defaults(func=run_spec_mode)

    compare_parser = commands.add_parser("compare", help="Render current/future diagrams and produce a diff")
    compare_parser.add_argument("--spec", help="Single spec file containing states.current and states.future")
    compare_parser.add_argument("--current", help="Current-state spec file")
    compare_parser.add_argument("--future", help="Future-state spec file")
    compare_parser.add_argument("--out-dir", default="output", help="Output directory for relative artifact paths")
    compare_parser.add_argument("--output-prefix", "-o", default="architecture_compare", help="Output prefix")
    compare_parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"], help="Output format")
    compare_parser.add_argument("--direction", choices=["TB", "LR", "BT", "RL"], help="Override diagram direction")
    compare_parser.set_defaults(func=run_compare_mode)

    aws_parser = commands.add_parser("aws-boto3", help="Fetch AWS resources via boto3 and render a rich diagram")
    aws_parser.add_argument("--profile", "-p", required=True, help="AWS profile name")
    aws_parser.add_argument("--region", "-r", required=True, help="AWS region")
    aws_parser.add_argument("--tag", "-t", default="", help="Optional tag keyword filter")
    aws_parser.add_argument("--out-dir", default="output", help="Output directory for relative artifact paths")
    aws_parser.add_argument("--output", "-o", default="aws_architecture", help="Output file prefix")
    aws_parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"], help="Output format")
    aws_parser.add_argument("--direction", choices=["TB", "LR", "BT", "RL"], help="Diagram direction override")
    aws_parser.add_argument("--export-json", help="Optional path to save fetched AWS inventory JSON")
    aws_parser.set_defaults(func=run_aws_boto3_mode)

    k8s_parser = commands.add_parser("k8s", help="Live Kubernetes workflows")
    k8s_commands = k8s_parser.add_subparsers(dest="k8s_command", required=True)

    discover_parser = k8s_commands.add_parser("discover", help="Auto-generate a spec and diagram from a live namespace")
    discover_parser.add_argument("--namespace", "-n", required=True, help="Kubernetes namespace to discover")
    discover_parser.add_argument("--context", help="kubectl context (defaults to current context)")
    discover_parser.add_argument("--title", help="Diagram title")
    discover_parser.add_argument("--direction", default="LR", choices=["TB", "LR", "BT", "RL"])
    discover_parser.add_argument("--out-dir", default="output", help="Output directory for relative artifact paths")
    discover_parser.add_argument("--output", "-o", default="k8s_namespace", help="Output file prefix")
    discover_parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"])
    discover_parser.add_argument("--export-spec", help="Also save the generated spec to this path")
    discover_parser.set_defaults(func=run_k8s_discover_mode)

    annotate_parser = k8s_commands.add_parser("annotate", help="Overlay live status onto an existing spec")
    annotate_parser.add_argument("--spec", required=True, help="Path to existing spec file")
    annotate_parser.add_argument("--state", help="State name when spec contains a 'states' object")
    annotate_parser.add_argument("--namespaces", help="Comma-separated namespaces to query (default: infer from spec)")
    annotate_parser.add_argument("--context", help="kubectl context (defaults to current context)")
    annotate_parser.add_argument("--out-dir", default="output", help="Output directory for relative artifact paths")
    annotate_parser.add_argument("--output", "-o", default="annotated", help="Output file prefix")
    annotate_parser.add_argument("--format", default="png", choices=["png", "pdf", "svg"])
    annotate_parser.add_argument("--direction", choices=["TB", "LR", "BT", "RL"], help="Override diagram direction")
    annotate_parser.add_argument("--export-spec", help="Also save the annotated spec to this path")
    annotate_parser.set_defaults(func=run_k8s_annotate_mode)

    summarize_parser = k8s_commands.add_parser("summarize", help="Print JSON summary of live namespace state")
    summarize_parser.add_argument("--namespaces", "-n", required=True, help="Comma-separated namespaces")
    summarize_parser.add_argument("--context", help="kubectl context (defaults to current context)")
    summarize_parser.set_defaults(func=run_k8s_summarize_mode)

    return parser


def run_spec_mode(args: argparse.Namespace) -> None:
    spec = load_data_file(Path(args.spec))
    state_spec = normalize_state_spec(spec, state=args.state)
    output_prefix = _resolve_output_prefix(args.output, args.out_dir)
    output = render_spec_diagram(state_spec, output_prefix, output_format=args.format, direction=args.direction)
    print(f"Diagram generated: {output}")


def run_compare_mode(args: argparse.Namespace) -> None:
    if args.spec:
        root_spec = load_data_file(Path(args.spec))
        if "states" not in root_spec:
            raise ValueError("--spec compare mode requires a 'states' object with 'current' and 'future'.")
        current_spec = normalize_state_spec(root_spec, state="current")
        future_spec = normalize_state_spec(root_spec, state="future")
    else:
        if not args.current or not args.future:
            raise ValueError("Provide either --spec or both --current and --future.")
        current_spec = normalize_state_spec(load_data_file(Path(args.current)))
        future_spec = normalize_state_spec(load_data_file(Path(args.future)))

    output_prefix = _resolve_output_prefix(args.output_prefix, args.out_dir)
    current_prefix = output_prefix.parent / f"{output_prefix.name}_current"
    future_prefix = output_prefix.parent / f"{output_prefix.name}_future"

    print("Rendering current-state diagram...")
    current_file = render_spec_diagram(current_spec, current_prefix, output_format=args.format, direction=args.direction)
    print("Rendering future-state diagram...")
    future_file = render_spec_diagram(future_spec, future_prefix, output_format=args.format, direction=args.direction)

    summary = compare_specs(current_spec, future_spec)
    summary_md = output_prefix.parent / f"{output_prefix.name}_diff.md"
    summary_json = output_prefix.parent / f"{output_prefix.name}_diff.json"
    write_compare_summary(summary, summary_md)
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Current diagram: {current_file}")
    print(f"Future diagram: {future_file}")
    print(f"Diff summary: {summary_md}")
    print(f"Diff JSON: {summary_json}")


def run_aws_boto3_mode(args: argparse.Namespace) -> None:
    try:
        import botocore.session  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "AWS boto3 mode requires botocore/boto3. Install with: uv add boto3"
        ) from exc

    try:
        from . import aws_boto3_mode as aws
    except Exception as exc:
        raise RuntimeError(
            "AWS boto3 mode requires the diagrams package and Graphviz. "
            "Install with: uv add diagrams (and ensure `dot -V` works)."
        ) from exc

    target = aws.AwsImportTarget(args.profile, args.region)
    session = botocore.session.Session(profile=target.profile_name)

    account = aws.get_account(target, session)
    account_aliases = aws.get_account_aliases(target, session)
    if not account:
        raise RuntimeError("Could not get AWS account info. Verify AWS profile and region.")

    print(f"Account: {account}")
    if account_aliases:
        print(f"Aliases: {', '.join(account_aliases)}")

    region_resources = aws.create_json(session, target)
    account_resources = aws.get_account_resources(session, target)

    data = {
        "accounts": [
            {
                "accountId": account,
                "accountAliases": account_aliases,
                "resources": account_resources,
                "regions": [{"regionId": target.region, "resources": region_resources}],
            }
        ]
    }

    if args.export_json:
        export_path = _resolve_output_file(args.export_json, args.out_dir)
        export_path.write_text(
            json.dumps(data, indent=2, cls=aws.DateTimeEncoder),
            encoding="utf-8",
        )
        print(f"AWS snapshot written to {export_path}")

    if getattr(aws, "ERRORS", None):
        print("Collection blind spots (partial AWS API failures):")
        for error in aws.ERRORS:
            print(f"- {error}")

    filtered = aws.filter_resources_by_tag(data, args.tag)
    output_prefix = _resolve_output_prefix(args.output, args.out_dir)
    aws.generate_diagram(
        filtered_resources=filtered,
        output_file=str(output_prefix),
        keyword=args.tag,
        output_format=args.format,
        direction_override=args.direction,
    )

    # Also produce standard GraphData artifacts (JSON + Mermaid)
    graph = dedupe_graph(aws.boto3_to_graph_data(filtered, args.profile, args.region))
    json_path = output_prefix.parent / f"{output_prefix.name}.graph.json"
    mermaid_path = output_prefix.parent / f"{output_prefix.name}.mmd"
    render_json(graph, json_path)
    render_mermaid(graph, mermaid_path, direction=args.direction or "LR")
    print(f"Wrote {json_path}")
    print(f"Wrote {mermaid_path}")
    print(f"Nodes: {len(graph.nodes)} | Edges: {len(graph.edges)}")

    # Emit blind spots report
    bs_report = collect_blind_spots(errors=list(getattr(aws, "ERRORS", [])))
    bs_json = output_prefix.parent / f"{output_prefix.name}.blindspots.json"
    bs_md = output_prefix.parent / f"{output_prefix.name}.blindspots.md"
    write_blind_spots_json(bs_report, bs_json)
    write_blind_spots_md(bs_report, bs_md)
    if bs_report["has_blind_spots"]:
        print(f"Wrote {bs_json}")
        print(f"Wrote {bs_md}")


def run_k8s_discover_mode(args: argparse.Namespace) -> None:
    spec = generate_namespace_spec(
        namespace=args.namespace,
        context=args.context,
        title=args.title,
        direction=args.direction,
    )

    if args.export_spec:
        spec_path = _resolve_output_file(args.export_spec, args.out_dir)
        _write_data_file(spec, spec_path)
        print(f"Spec written to {spec_path}")

    output_prefix = _resolve_output_prefix(args.output, args.out_dir)
    output = render_spec_diagram(spec, output_prefix, output_format=args.format)
    print(f"Diagram generated: {output}")


def run_k8s_annotate_mode(args: argparse.Namespace) -> None:
    spec = load_data_file(Path(args.spec))
    state_spec = normalize_state_spec(spec, state=args.state)

    namespaces = None
    if args.namespaces:
        namespaces = [name.strip() for name in args.namespaces.split(",") if name.strip()]

    annotated = annotate_spec(state_spec, namespaces=namespaces, context=args.context)

    if args.export_spec:
        spec_path = _resolve_output_file(args.export_spec, args.out_dir)
        _write_data_file(annotated, spec_path)
        print(f"Annotated spec written to {spec_path}")

    output_prefix = _resolve_output_prefix(args.output, args.out_dir)
    output = render_spec_diagram(annotated, output_prefix, output_format=args.format, direction=args.direction)
    print(f"Diagram generated: {output}")


def run_k8s_summarize_mode(args: argparse.Namespace) -> None:
    namespaces = [name.strip() for name in args.namespaces.split(",") if name.strip()]
    for namespace in namespaces:
        print(json.dumps(summarize_namespace(namespace, context=args.context), indent=2))


def main() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] in COMPOSITE_COMMANDS:
        composite_args = build_composite_parser().parse_args(argv)
        try:
            composite_args.func(composite_args)
        except (RuntimeError, ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise SystemExit(str(exc)) from exc
        return

    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir).resolve()

    sources = set(args.source or [])
    if args.helm_chart:
        sources.add("kubernetes")

    discovered = {"json": [], "tfstate": [], "tfjson": [], "k8s": []}
    if args.discover:
        discovered = discover_files(root)
        if discovered["json"]:
            sources.add("json")
        if discovered["tfstate"] or discovered["tfjson"]:
            sources.add("terraform")
        if discovered["k8s"]:
            sources.add("kubernetes")

    if not sources:
        raise SystemExit("No sources selected. Use --source ... or --discover")

    graphs: list[GraphData] = []
    blind_spot_errors: list[str] = []
    blind_spot_empty: list[str] = []

    if "aws" in sources:
        try:
            g = collect_from_aws_cli(profile=args.profile, region=args.region)
            if not g.nodes:
                blind_spot_empty.append("aws: no resources discovered")
            graphs.append(g)
        except Exception as exc:
            blind_spot_errors.append(f"aws: {exc}")

    if "json" in sources:
        json_files = [Path(path).resolve() for path in args.json] or discovered["json"]
        if json_files:
            try:
                g = collect_from_json(json_files)
                if not g.nodes:
                    blind_spot_empty.append("json: no nodes produced")
                graphs.append(g)
            except Exception as exc:
                blind_spot_errors.append(f"json: {exc}")

    if "terraform" in sources:
        tf_files = [Path(path).resolve() for path in args.terraform] or (discovered["tfstate"] + discovered["tfjson"])
        if tf_files:
            try:
                g = collect_from_terraform(tf_files)
                if not g.nodes:
                    blind_spot_empty.append("terraform: no resources found")
                graphs.append(g)
            except Exception as exc:
                blind_spot_errors.append(f"terraform: {exc}")

    if "kubernetes" in sources:
        k8s_files = [Path(path).resolve() for path in args.k8s] or discovered["k8s"]
        helm_charts = [Path(path).resolve() for path in args.helm_chart]
        helm_values = [Path(path).resolve() for path in args.helm_values]

        helm_docs = []
        if helm_charts:
            try:
                helm_docs = collect_from_helm_charts(
                    chart_paths=helm_charts,
                    values_files=helm_values,
                    namespace=args.helm_namespace,
                    release_prefix=args.helm_release_prefix,
                )
            except Exception as exc:
                blind_spot_errors.append(f"helm: {exc}")

        try:
            g = collect_from_kubernetes(
                k8s_files,
                use_live_cluster=args.live_k8s,
                extra_docs=helm_docs,
            )
            if not g.nodes:
                blind_spot_empty.append("kubernetes: no resources found")
            graphs.append(g)
        except Exception as exc:
            blind_spot_errors.append(f"kubernetes: {exc}")

    if not graphs:
        raise SystemExit("No data collected from selected sources")

    merged = _merge_graphs(graphs)

    artifact_dir = out_dir / args.name if (args.artifact_folder or args.zip_artifacts) else out_dir
    json_path = artifact_dir / f"{args.name}.graph.json"
    mermaid_path = artifact_dir / f"{args.name}.mmd"

    render_json(merged, json_path)
    render_mermaid(merged, mermaid_path, direction=args.direction)

    rendered_images: list[Path] = []
    rendered_diagrams: list[Path] = []
    try:
        if args.svg:
            rendered_images.append(
                render_mermaid_image(
                    mermaid_path,
                    artifact_dir / f"{args.name}.svg",
                    image=args.mermaid_image,
                    background=args.mermaid_background,
                    theme=args.mermaid_theme,
                )
            )

        if args.png:
            rendered_images.append(
                render_mermaid_image(
                    mermaid_path,
                    artifact_dir / f"{args.name}.png",
                    image=args.mermaid_image,
                    background=args.mermaid_background,
                    theme=args.mermaid_theme,
                )
            )

        for output_format in args.diagram_format or []:
            rendered_diagrams.append(
                render_with_diagrams(
                    merged,
                    artifact_dir / f"{args.name}.diagram",
                    output_format=output_format,
                    direction=args.direction,
                    title=args.diagram_title,
                )
            )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Wrote {json_path}")
    print(f"Wrote {mermaid_path}")
    for image_path in rendered_images:
        print(f"Wrote {image_path}")
    for diagram_path in rendered_diagrams:
        print(f"Wrote {diagram_path}")
    if args.zip_artifacts:
        archive = shutil.make_archive(str(out_dir / args.name), "zip", root_dir=artifact_dir)
        print(f"Wrote {archive}")

    bs_report = collect_blind_spots(errors=blind_spot_errors, empty_sources=blind_spot_empty)
    if bs_report["has_blind_spots"]:
        bs_json = artifact_dir / f"{args.name}.blindspots.json"
        bs_md = artifact_dir / f"{args.name}.blindspots.md"
        write_blind_spots_json(bs_report, bs_json)
        write_blind_spots_md(bs_report, bs_md)
        print(f"Wrote {bs_json}")
        print(f"Wrote {bs_md}")

    print(f"Nodes: {len(merged.nodes)} | Edges: {len(merged.edges)}")


if __name__ == "__main__":
    main()
