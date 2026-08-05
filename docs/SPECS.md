# Architecture Spec Workflows

Use spec workflows when the architecture is known and should be documented explicitly rather than discovered from infrastructure files. Specs are deterministic YAML or JSON documents that describe nodes, edges, clusters, layout direction, and Graphviz attributes.

## Recommended agent loop

Validate before invoking Graphviz:

```bash
uv run diagram-gen spec --spec examples/spec-architecture.yaml --check
```

Render every required format in one process:

```bash
uv run diagram-gen spec \
  --spec examples/spec-architecture.yaml \
  --out-dir output \
  --output architecture \
  --format svg \
  --format png
```

For a documentation tree containing multiple specs, validate or render the whole set in stable path order:

```bash
uv run diagram-gen spec-batch --spec-dir docs/diagrams/specs --check

uv run diagram-gen spec-batch \
  --spec-dir docs/diagrams/specs \
  --out-dir docs/diagrams/rendered \
  --format svg \
  --format png
```

Batch mode searches `*.yaml`, `*.yml`, and `*.json` by default. Add `--recursive` to preserve nested source paths under the output directory, or repeat `--pattern` to select another naming convention. Every matching spec is validated before the first artifact is written. Empty matches and output-name collisions are errors, so a mistyped path or duplicate stem cannot produce a false-success or silently overwrite another render.

Both commands print per-spec node, edge, and cluster counts. Batch mode also prints aggregate counts and the number of rendered artifacts.

## Spec structure

```yaml
title: Example Architecture
direction: LR
graph_attr:
  ranksep: "1.0"
  nodesep: "0.65"
clusters:
  - id: source
    label: Source systems
    graph_attr:
      bgcolor: "#eff6ff"
nodes:
  - id: repository
    label: "Content repository\nMarkdown source"
    icon: onprem.vcs.Github
    cluster: source
    attrs:
      color: "#2563eb"
  - id: build
    label: Build workflow
    icon: onprem.ci.GithubActions
edges:
  - from: repository
    to: build
    label: exact commit SHA
    style: dashed
    attrs:
      minlen: "2"
```

Top-level fields:

- `title`: diagram title; titles render above the graph by default.
- `direction`: `TB`, `LR`, `BT`, or `RL`.
- `graph_attr`, `node_attr`, `edge_attr`: default Graphviz attributes.
- `clusters`: optional visual groups. A cluster can name another cluster with `parent`.
- `nodes`: entities with stable `id` values, labels, explicit icons, optional cluster membership, status, and Graphviz `attrs`. Graphviz output preserves authored line breaks and automatically wraps long label lines, including unbroken resource IDs and IP addresses, to prevent text overlap around fixed-size icon nodes.
- `edges`: relationships using `from` and `to` node IDs.

The validator rejects malformed collections, duplicate node or cluster IDs, unknown cluster references, cyclic cluster parents, unknown edge endpoints, invalid directions, invalid edge modes, and non-object attribute blocks before rendering begins.

## Edge direction and layout controls

An edge defaults to `mode: forward`. The supported modes are:

- `forward`: `from` points to `to`.
- `reverse`: visual arrow points from `to` to `from` without changing the declared IDs.
- `undirected`: relationship renders without a forward arrow.

Common edge fields—`label`, `color`, `style`, `penwidth`, and `dir`—can be written directly. Put additional Graphviz controls in `attrs`:

```yaml
edges:
  - from: monitoring
    to: application
    label: observes
    attrs:
      constraint: "false"
      minlen: "2"
      weight: "0.5"
```

Useful layout controls include:

- `constraint: "false"`: keep a secondary relationship from changing rank placement.
- `minlen`: request more rank separation between connected nodes.
- `weight`: increase or reduce an edge's influence on layout.
- `xlabel`: add a label that does not reserve the same routing space as `label`.

Use strings for Graphviz attribute values. Explicit top-level edge fields override the same key in `attrs`.

## States and comparisons

A spec can share top-level defaults while defining `states.current` and `states.future`. Select a state with `spec --state <name>`, or render and compare both standard states with:

```bash
uv run diagram-gen compare \
  --spec specs/migration.yaml \
  --output-prefix output/migration \
  --format svg
```

## Container usage

The project image includes Graphviz and the render dependencies:

```bash
podman run --rm --userns=keep-id \
  --volume "$PWD:/workspace:Z" \
  diagram-gen:local spec-batch \
  --spec-dir docs/diagrams/specs \
  --out-dir docs/diagrams/rendered \
  --format svg --format png
```

The image's non-root `diagram` user owns its virtual environment, so repository checks can also be run inside the image with `uv run`.

## Review checklist

After rendering:

1. Confirm the printed counts match the intended scope.
2. Inspect PNG output at full resolution; successful Graphviz output can still contain confusing edge routes.
3. Confirm SVG icons are embedded when the artifact must be self-contained.
4. Rerender and compare checksums when deterministic output matters.
5. Commit the spec and every supported rendered format together.
