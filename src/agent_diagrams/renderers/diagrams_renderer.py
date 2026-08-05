from __future__ import annotations

import base64
import importlib
import re
import textwrap
from pathlib import Path
from typing import Callable

from agent_diagrams.icon_catalog import (
    ICON_ALIASES,
    resolve_asset_path,
    resolve_node_icon,
)
from agent_diagrams.model import GraphData

try:
    from diagrams import Diagram, Edge
    from diagrams.custom import Custom
    from diagrams.generic.blank import Blank

    DIAGRAMS_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependent
    Diagram = Edge = Custom = Blank = None
    DIAGRAMS_IMPORT_ERROR = exc


DEFAULT_GRAPH_ATTR = {
    "splines": "spline",
    "ranksep": "1.0",
    "nodesep": "0.75",
    "pad": "0.4",
}

DEFAULT_LABEL_WIDTH = 20


def wrap_graphviz_label(label: str, *, width: int = DEFAULT_LABEL_WIDTH) -> str:
    """Wrap a display label without changing its source graph value.

    Explicit line breaks are preserved and long tokens (for example IPv6
    addresses or resource IDs) are split deterministically so labels stay
    within the spacing reserved around fixed-size icon nodes.
    """
    if width < 1:
        raise ValueError("Graphviz label width must be at least 1.")

    wrapper = textwrap.TextWrapper(
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=True,
        drop_whitespace=True,
    )
    wrapped_lines: list[str] = []
    for line in label.split("\n"):
        wrapped_lines.extend(wrapper.wrap(line) or [""])
    return "\n".join(wrapped_lines)


def _require_diagrams() -> None:
    if DIAGRAMS_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Non-Mermaid rendering requested, but the 'diagrams' package is not installed. "
            f"Install it first (original import error: {DIAGRAMS_IMPORT_ERROR})."
        )


def _dotted_import(path: str):
    module_name, cls_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)


def load_icon_factory(icon_ref: str | None) -> Callable:
    if not icon_ref:
        return Blank

    asset_path = resolve_asset_path(icon_ref)
    if asset_path is not None:
        return lambda label, **kwargs: Custom(label, str(asset_path), **kwargs)

    try:
        return _dotted_import(icon_ref)
    except (ImportError, AttributeError, ValueError):
        return Blank


def _resolve_icon(
    kind: str,
    label: str,
    node_id: str,
    *,
    explicit_icon: str | None = None,
):
    _require_diagrams()
    icon_ref = resolve_node_icon(
        kind,
        label,
        node_id,
        explicit_icon=explicit_icon,
    )
    return load_icon_factory(icon_ref)


def unresolved_icon_nodes(graph: GraphData) -> list[dict[str, str]]:
    unresolved = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        explicit_icon = node.attrs.get("icon")
        if not isinstance(explicit_icon, str):
            explicit_icon = None
        icon_ref = resolve_node_icon(
            node.kind,
            node.label,
            node.id,
            explicit_icon=explicit_icon,
        )
        if icon_ref is None:
            unresolved.append({"id": node.id, "kind": node.kind, "label": node.label})
    return unresolved


def _inline_svg_image_refs(svg_path: Path) -> None:
    raw = svg_path.read_text(encoding="utf-8")
    pattern = re.compile(r'(xlink:href|href)="([^"]+)"')

    def replace(match: re.Match[str]) -> str:
        attr = match.group(1)
        href = match.group(2)
        if href.startswith("data:"):
            return match.group(0)
        icon_path = Path(href)
        if not icon_path.is_file():
            return match.group(0)

        suffix = icon_path.suffix.lower()
        if suffix not in {".png", ".svg"}:
            return match.group(0)

        mime = "image/png" if suffix == ".png" else "image/svg+xml"
        encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
        return f'{attr}="data:{mime};base64,{encoded}"'

    updated = pattern.sub(replace, raw)
    svg_path.write_text(updated, encoding="utf-8")


def render_with_diagrams(
    graph: GraphData,
    output_prefix: Path,
    *,
    output_format: str = "png",
    direction: str = "LR",
    title: str = "Infrastructure Diagram",
) -> Path:
    _require_diagrams()

    graph_attr = dict(DEFAULT_GRAPH_ATTR)
    output_prefix = output_prefix.resolve()
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    node_objs: dict[str, object] = {}
    sorted_nodes = sorted(graph.nodes, key=lambda n: n.id)
    sorted_edges = sorted(graph.edges, key=lambda e: (e.src, e.dst, e.rel, e.source))

    with Diagram(
        title,
        filename=str(output_prefix),
        show=False,
        outformat=output_format,
        direction=direction,
        graph_attr=graph_attr,
    ):
        for node in sorted_nodes:
            explicit_icon = node.attrs.get("icon")
            if not isinstance(explicit_icon, str):
                explicit_icon = None
            icon_factory = _resolve_icon(
                node.kind,
                node.label,
                node.id,
                explicit_icon=explicit_icon,
            )
            node_objs[node.id] = icon_factory(wrap_graphviz_label(node.label))

        for edge in sorted_edges:
            src = node_objs.get(edge.src)
            dst = node_objs.get(edge.dst)
            if src is None or dst is None:
                continue
            src >> Edge(label=edge.rel) >> dst

    output_path = output_prefix.parent / f"{output_prefix.name}.{output_format}"
    if output_format == "svg":
        _inline_svg_image_refs(output_path)
    return output_path
