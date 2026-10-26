"""Static Terraform collection; never runs Terraform or evaluates expressions."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import hcl2
from lark.exceptions import LarkError

from .model import Edge, GraphData, Node

_IDENTIFIER = r"[A-Za-z_][\w-]*"
_ADDRESS = re.compile(
    rf"(?<![\w.-])(?:data\.{_IDENTIFIER}\.{_IDENTIFIER}|module\.{_IDENTIFIER}|{_IDENTIFIER}\.{_IDENTIFIER})"
)
_STRING = re.compile(r'"(?:\\.|[^"\\])*"')


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _strings(key)
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _expressions(value: str) -> Iterator[str]:
    """Extract interpolations, balancing braces and quoted strings."""
    index = 0
    while index < len(value):
        start = value.find("${", index)
        if start < 0:
            return
        if start and value[start - 1] == "$":  # escaped Terraform interpolation
            index = start + 2
            continue
        end, depth, quoted, escaped = start + 2, 1, False, False
        while end < len(value) and depth:
            char = value[end]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif not quoted:
                depth += (char == "{") - (char == "}")
            end += 1
        expression = value[start + 2 : end - 1] if not depth else value[start + 2 :]
        # Literal strings inside expressions are not resource references. Their
        # nested interpolations, however, can contain references.
        for literal in _STRING.findall(expression):
            yield from _expressions(literal[1:-1])
        yield _STRING.sub('""', expression)
        index = end


def _blocks(raw: dict, key: str) -> Iterator[tuple[list[str], dict]]:
    blocks = raw.get(key, [])
    if isinstance(blocks, dict):
        blocks = [blocks]
    for block in blocks:
        for label, contents in block.items():
            if key == "module":
                yield [label], contents
            else:
                for name, config in contents.items():
                    yield [label, name], config


def expand_terraform_paths(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            # A directory is one module. Do not silently merge child modules.
            files.update(path.glob("*.tf"))
            files.update(path.glob("*.tf.json"))
        else:
            files.add(path)
    return sorted(p.resolve() for p in files)


def collect_terraform(paths: list[Path], inputs: list[str]) -> GraphData:
    files = expand_terraform_paths(paths)
    graph = GraphData(
        metadata={"source": "terraform", "inputs": inputs, "warnings": []}
    )
    warnings: list[str] = graph.metadata["warnings"]
    if not files:
        warnings.append("No Terraform files found in the selected module directories.")
        return graph
    common = Path(os.path.commonpath([str(p.parent) for p in files]))
    # Preserve existing IDs for single-module collection; qualify independent
    # directories so identical declarations in separate modules cannot merge.
    entries: dict[tuple[str, str], tuple[Node, dict, bool]] = {}

    def add(
        scope: str, address: str, kind: str, config: dict, *, state: bool = False
    ) -> None:
        key = (scope, address)
        node_id = f"tf:{scope + ':' if scope else ''}{address}"
        node = Node(node_id, address, f"tf.{kind}", "terraform", config)
        if key in entries:
            previous, old_config, was_state = entries[key]
            # Config and state for the same resource are one observed entity.
            node = previous
            config = {**old_config, **config}
            state = state and was_state
            node.attrs = config
        entries[key] = (node, config, state)

    for path in files:
        scope = path.parent.relative_to(common).as_posix()
        scope = "" if scope == "." else scope
        try:
            if path.suffix == ".tf":
                with path.open(encoding="utf-8") as stream:
                    raw = hcl2.load(stream)
            else:
                raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("Expected a Terraform object")
            if "resources" in raw:
                for resource in raw["resources"]:
                    prefix = resource.get("module", "")
                    mode = "data." if resource.get("mode") == "data" else ""
                    address = f"{mode}{resource['type']}.{resource['name']}"
                    if prefix:
                        address = f"{prefix}.{address}"
                    add(scope, address, resource["type"], resource, state=True)
                continue
            for block_type in ("resource", "data", "module"):
                for labels, config in _blocks(raw, block_type):
                    address = ".".join(labels)
                    if block_type != "resource":
                        address = f"{block_type}.{address}"
                    add(
                        scope,
                        address,
                        "module" if block_type == "module" else labels[0],
                        config,
                    )
            if raw.get("locals") or raw.get("variable"):
                warnings.append(
                    f"{path.name}: variables/locals are not evaluated; indirect dependencies may be missing."
                )
        except (OSError, ValueError, KeyError, TypeError, LarkError) as exc:
            warnings.append(f"{path.name}: unable to parse Terraform: {exc}")

    edges: set[tuple[str, str, str]] = set()
    for (scope, address), (node, config, state) in sorted(entries.items()):
        graph.add_node(node)
        if "count" in config or "for_each" in config:
            warnings.append(
                f"{address}: count/for_each is shown as one declaration, not expanded instances."
            )
        references: set[tuple[str, str]] = set()
        for explicit in _strings(config.get("depends_on", [])):
            expressions = list(_expressions(explicit))
            references.add(
                ((expressions[0] if expressions else explicit).strip(), "depends_on")
            )
        implicit_config = {k: v for k, v in config.items() if k != "depends_on"}
        if not state:
            for value in _strings(implicit_config):
                for expression in _expressions(value):
                    references.update(
                        (match.group(), "references")
                        for match in _ADDRESS.finditer(expression)
                        if match.group().split(".")[0]
                        not in {
                            "var",
                            "local",
                            "path",
                            "count",
                            "each",
                            "self",
                            "terraform",
                        }
                    )
        for instance in config.get("instances", []):
            references.update(
                (dep, "depends_on") for dep in instance.get("dependencies", [])
            )
        for target, relationship in sorted(references):
            # Resolve indexed references to their declared resource, not invented
            # count/for_each instances. Prefer full state addresses when present.
            candidates = [target, re.sub(r"\[[^\]]*\]", "", target)]
            target_entry = next(
                (
                    entries[(scope, item)]
                    for item in candidates
                    if (scope, item) in entries
                ),
                None,
            )
            if target_entry is None:
                warnings.append(
                    f"{address}: unresolved {relationship} target '{target}'."
                )
                continue
            if node.id != target_entry[0].id:
                edges.add((node.id, target_entry[0].id, relationship))
        if node.kind == "tf.module":
            warnings.append(
                f"{address}: module call shown as one node; child resources and outputs are not expanded."
            )
    for src, dst, rel in sorted(edges):
        graph.add_edge(Edge(src, dst, rel, "terraform"))
    graph.metadata["warnings"] = sorted(set(warnings))
    graph.metadata["collection_mode"] = "static-declarations-and-state"
    return graph
