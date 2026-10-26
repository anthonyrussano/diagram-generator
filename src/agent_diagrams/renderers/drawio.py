"""Export Graphviz layouts as editable, self-contained diagrams.net XML.

Uses the Graphviz executable already needed by Diagrams. Nodes, labels,
clusters and connectors remain separate cells; icons are embedded locally.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _label(item: dict) -> str:
    label = str(item.get("label") or item.get("xlabel") or "")
    if label == r"\N":
        label = item.get("name", "")
    return label.replace(r"\n", "\n").replace(r"\l", "\n").replace(r"\r", "\n")


def _style(item: dict, *, cluster: bool = False) -> dict[str, str]:
    shape = item.get("shape", "box")
    styles = set(item.get("style", "").split(","))
    result = {
        "html": "0",
        "whiteSpace": "wrap",
        "fontFamily": item.get("fontname", "Sans-Serif"),
        "fontSize": item.get("fontsize", "13"),
        "fontColor": item.get("fontcolor", "#2D3436"),
        "strokeColor": item.get("color", "#7B8894"),
        "strokeWidth": item.get("penwidth", "1"),
        "fillColor": item.get("fillcolor", item.get("bgcolor", "#ffffff"))
        if "filled" in styles or cluster
        else "none",
        "rounded": "1" if "rounded" in styles else "0",
    }
    if "dashed" in styles or "dotted" in styles:
        result["dashed"] = "1"
    if shape in {"ellipse", "oval", "circle", "doublecircle"}:
        result["shape"] = "ellipse"
    elif shape == "diamond":
        result["shape"] = "rhombus"
    else:
        result["shape"] = "rectangle"
    if cluster:
        result.update(
            {
                "container": "1",
                "collapsible": "0",
                "verticalAlign": "top",
                "spacingTop": "5",
                "recursiveResize": "0",
            }
        )
    return result


def _style_string(values: dict[str, Any]) -> str:
    # A semicolon is an mxGraph style separator, never part of a scalar value.
    return (
        ";".join(
            f"{key}={str(value).replace(';', '')}" for key, value in values.items()
        )
        + ";"
    )


def _image_style(item: dict, asset_dir: Path) -> dict[str, str]:
    if not item.get("image"):
        return {}
    icon = Path(item["image"])
    if not icon.is_absolute():
        icon = asset_dir / icon
    if not icon.is_file():
        raise RuntimeError(f"Cannot embed draw.io icon: {icon}")
    mime = mimetypes.guess_type(icon.name)[0]
    if mime not in {"image/png", "image/jpeg", "image/svg+xml", "image/gif"}:
        raise RuntimeError(f"Unsupported draw.io icon type: {icon}")
    encoded = base64.b64encode(icon.read_bytes()).decode("ascii")
    # mxGraph's image style uses data:mime,base64 (without the ;base64 marker).
    return {
        "shape": "image",
        "image": f"data:{mime},{encoded}",
        "imageAspect": "1",
        "aspect": "fixed",
        "verticalLabelPosition": "middle",
        "verticalAlign": "bottom",
    }


def _bend_points(edge: dict) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for token in edge.get("pos", "").replace(";", " ").split():
        parts = token.split(",")
        if len(parts) != 2:  # skip the e,/s, arrow-endpoint markers
            continue
        point = (float(parts[0]), float(parts[1]))
        if points and point == points[-1]:
            continue
        # Graphviz repeats cubic control points even on orthogonal segments.
        # Keep the actual turns, approximating splines with editable polylines.
        while len(points) >= 2:
            a, b = points[-2:]
            cross = (b[0] - a[0]) * (point[1] - b[1]) - (b[1] - a[1]) * (
                point[0] - b[0]
            )
            if abs(cross) > 0.01:
                break
            points.pop()
        points.append(point)
    return points[1:-1]


def layout_to_drawio(
    layout: dict, dot_path: Path, output: Path, *, asset_dir: Path | None = None
) -> Path:
    asset_dir = asset_dir or dot_path.parent
    objects = {item["_gvid"]: item for item in layout.get("objects", [])}
    clusters = {
        index: item
        for index, item in objects.items()
        if item.get("name", "").startswith("cluster")
        and "bb" in item
        and "invis" not in item.get("style", "").split(",")
    }
    nodes = {
        index: item
        for index, item in objects.items()
        if "pos" in item
        and index not in clusters
        and "invis" not in item.get("style", "").split(",")
    }
    bb = [float(v) for v in layout.get("bb", "0,0,0,0").split(",")]
    left, top = bb[0], bb[3]
    margin = 30.0

    # Nested clusters include all descendant node IDs in Graphviz output.
    # Choose the smallest containing cluster as each cell's immediate parent.
    boxes = {
        index: [float(v) for v in item["bb"].split(",")]
        for index, item in clusters.items()
    }
    parents: dict[int, int] = {}
    for index in clusters | nodes:
        candidates = [
            parent
            for parent, item in clusters.items()
            if parent != index
            and index in item.get("nodes", []) + item.get("subgraphs", [])
        ]
        if candidates:
            parents[index] = min(
                candidates,
                key=lambda p: (boxes[p][2] - boxes[p][0]) * (boxes[p][3] - boxes[p][1]),
            )

    file = ET.Element(
        "mxfile", host="app.diagrams.net", type="device", compressed="false"
    )
    diagram = ET.SubElement(
        file, "diagram", id="diagram", name=_label(layout) or "Architecture"
    )
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        grid="1",
        gridSize="10",
        page="0",
        pageWidth=_number(bb[2] - left + 2 * margin),
        pageHeight=_number(top - bb[1] + 2 * margin),
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    def origin(parent: int | None) -> tuple[float, float]:
        if parent is None:
            return left - margin, top + margin
        box = boxes[parent]
        return box[0], box[3]

    # Parent cells must precede children for reliable import in mxGraph.
    def depth(index: int) -> int:
        return 1 + depth(parents[index]) if index in parents else 0

    for index in sorted(clusters | nodes, key=lambda i: (depth(i), i)):
        item = objects[index]
        if "invis" in item.get("style", "").split(","):
            continue
        parent = parents.get(index)
        origin_x, origin_y = origin(parent)
        if index in clusters:
            x0, y0, x1, y1 = boxes[index]
            x, y, width, height = x0, y1, x1 - x0, y1 - y0
        else:
            x, y = [float(v) for v in item["pos"].split(",")[:2]]
            width, height = float(item["width"]) * 72, float(item["height"]) * 72
            x, y = x - width / 2, y + height / 2
        style = _style(item, cluster=index in clusters)
        style.update(_image_style(item, asset_dir))
        cell = ET.SubElement(
            root,
            "mxCell",
            id=f"v{index}",
            value=_label(item),
            vertex="1",
            parent=f"v{parent}" if parent is not None else "1",
            style=_style_string(style),
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            x=_number(x - origin_x),
            y=_number(origin_y - y),
            width=_number(width),
            height=_number(height),
            **{"as": "geometry"},
        )

    for index, edge in enumerate(layout.get("edges", [])):
        if "invis" in edge.get("style", "").split(","):
            continue
        if (
            edge["tail"] not in nodes
            or edge["head"] not in nodes
            or any(
                "invis" in nodes[end].get("style", "").split(",")
                for end in (edge["tail"], edge["head"])
            )
        ):
            continue
        direction = edge.get(
            "dir", "forward" if layout.get("directed", True) else "none"
        )
        styles = {
            "edgeStyle": "none",
            "rounded": "1",
            "html": "0",
            "endArrow": "classic" if direction in {"forward", "both"} else "none",
            "startArrow": "classic" if direction in {"back", "both"} else "none",
            "strokeColor": edge.get("color", "#7B8894"),
            "strokeWidth": edge.get("penwidth", "1"),
            "fontSize": edge.get("fontsize", "10"),
            "fontColor": edge.get("fontcolor", "#2D3436"),
        }
        if "dashed" in edge.get("style", "") or "dotted" in edge.get("style", ""):
            styles["dashed"] = "1"
        cell = ET.SubElement(
            root,
            "mxCell",
            id=f"e{index}",
            value=_label(edge),
            edge="1",
            parent="1",
            source=f"v{edge['tail']}",
            target=f"v{edge['head']}",
            style=_style_string(styles),
        )
        geometry = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        bends = _bend_points(edge)
        if bends:
            points = ET.SubElement(geometry, "Array", **{"as": "points"})
            for x, y in bends:
                ET.SubElement(
                    points,
                    "mxPoint",
                    x=_number(x - left + margin),
                    y=_number(top - y + margin),
                )

    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(file)
    ET.ElementTree(file).write(output, encoding="utf-8", xml_declaration=True)
    return output


def export_dot_to_drawio(
    dot_path: Path, output: Path, *, timeout: int = 90, asset_dir: Path | None = None
) -> Path:
    dot_path = dot_path.resolve()
    asset_dir = asset_dir.resolve() if asset_dir is not None else dot_path.parent
    try:
        result = subprocess.run(
            ["dot", "-Tjson0", str(dot_path)],
            cwd=asset_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Graphviz 'dot' is required for draw.io export.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Graphviz draw.io layout timed out after {timeout} seconds: {dot_path}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Graphviz draw.io layout failed for {dot_path}: {exc.stderr}"
        ) from exc
    return layout_to_drawio(
        json.loads(result.stdout), dot_path, output, asset_dir=asset_dir
    )
