# diagram-gen repository analysis

Analyzed on 2026-08-03 with `uv` 0.11.29 and uv-managed Python 3.12.13.

## Architecture summary

The installed `diagram-gen` entry point dispatches either the baseline graph pipeline or one of four composite command families.

Baseline pipeline:

1. Independent AWS CLI, JSON, Terraform, Kubernetes, and Helm collectors produce `GraphData` objects.
2. The CLI merges them and `normalize.py` deduplicates nodes and edges.
3. The canonical graph is written as JSON and Mermaid source.
4. Optional native/Podman/Docker Mermaid or python-diagrams/Graphviz renderers produce images.
5. Collector errors and empty sources produce JSON and Markdown blind-spots reports when at least one graph was collected.

Composite workflows:

- `spec`: validates and renders a YAML/JSON architecture spec.
- `compare`: renders current/future specs and writes a structured diff.
- `k8s`: discovers, annotates, or summarizes live namespace state through `kubectl`.
- `aws-boto3`: performs richer AWS discovery, renders through python-diagrams, and converts the result back to canonical `GraphData` artifacts.

## Generated diagrams

| Diagram | Nodes | Edges | Review artifacts |
| --- | ---: | ---: | --- |
| Runtime and external boundaries | 23 | 33 | [graph JSON](runtime-flow/runtime-flow.graph.json), [Mermaid](runtime-flow/runtime-flow.mmd), [SVG](runtime-flow/runtime-flow.svg), [PNG](runtime-flow/runtime-flow.png) |
| Python modules and material dependencies | 20 | 31 | [graph JSON](module-dependencies/module-dependencies.graph.json), [Mermaid](module-dependencies/module-dependencies.mmd), [SVG](module-dependencies/module-dependencies.svg), [PNG](module-dependencies/module-dependencies.png) |

Both diagram sets were generated twice through `diagram-gen --source json`. The graph JSON and Mermaid SHA-256 hashes were unchanged on the second run. Both graphs have unique node IDs and no dangling edge endpoints.

## Verification

- `uv sync --extra dev`: passed.
- `uv run pytest tests/ -v`: 133 passed in 0.07 seconds.
- `uv run python -m py_compile src/agent_diagrams/*.py src/agent_diagrams/renderers/*.py`: passed.
- `uv run diagram-gen --help`: passed.
- Composite help for `spec`, `compare`, `k8s`, and `aws-boto3`: passed.
- Explicit JSON-source smoke runs: passed and printed node/edge counts.
- Artifact-folder and ZIP smoke runs: passed; each ZIP contains its canonical graph JSON and Mermaid source.
- Rootless Podman image build and in-image pytest: passed.
- Container toolchain smoke: AWS CLI 2.36.14, kubectl 1.36.3, Helm 4.2.3, Mermaid CLI 11.16.0, and Graphviz 2.43.0.
- Host-side Mermaid rendering through Podman and self-contained in-image Mermaid/Graphviz rendering: passed for SVG and PNG.
- Repository-root discovery smoke: passed mechanically with 47 nodes and 66 edges, but exposed over-broad discovery described below.

## Dependency boundaries

- Required Python runtime dependency: PyYAML.
- Development dependency: pytest.
- Optional Python rendering dependency: python-diagrams.
- Optional rich AWS dependencies: boto3/botocore and python-diagrams.
- External executables by feature: AWS CLI, kubectl, Helm, Mermaid CLI or Docker/Podman, and Graphviz `dot`.
- Container-based Mermaid rendering pulls/runs the configured official Mermaid CLI image.

Podman is installed on this host; Docker, host Graphviz, AWS CLI, kubectl, and Helm remain absent. The self-contained Podman image validated both rendering stacks and all bundled tools. Live source collection was not run against real AWS or Kubernetes systems, so credentials, permissions, API reachability, and inventory coverage remain unverified.

## Findings and blind spots

1. Repository-root discovery is too broad. `discover_files()` recursively includes every JSON file, including `.venv`, `output`, and test snapshots. In this workspace it selected nine JSON files, including three package metadata files and generated outputs. The documented `--discover --root .` quick start can therefore diagram unrelated or stale data and can re-ingest prior generated graphs.
2. The baseline AWS collector is all-or-nothing per source. It performs ten API calls before building nodes; one denied or failed call discards otherwise successful inventory. The outer CLI reports the source failure only if another graph is available, so partial-permission robustness is weaker than the repository mission implies.
3. Baseline graph inputs are not validated for referential integrity. JSON, Terraform `depends_on`, and Kubernetes owner references can create edges to absent nodes. Mermaid will implicitly display undeclared endpoints, while the python-diagrams renderer silently skips those edges, so output formats can disagree.
4. Terraform collection is intentionally shallow: state creates one node per resource block and no edges; `.tf.json` only extracts explicit `depends_on`. It does not represent state instances or inferred references.
5. Live Kubernetes visibility is partial. The baseline path uses `kubectl get all`, which omits several resource families, while the composite path turns most per-resource query failures into empty lists without a blind-spots artifact.
6. `agent_diagram_builder.py` duplicates older spec-rendering logic outside the packaged entry point, and `generate-images.py` is a standalone helper. Neither is referenced by the installed `diagram-gen` entry point, creating a maintenance/documentation ambiguity.

## Suggested priority order

1. Add discovery exclusions for VCS/virtualenv/cache/output/test paths, with an explicit override.
2. Make AWS API collection resilient per service and always persist blind spots even when no graph succeeds.
3. Validate edge endpoints before rendering and report or reject dangling relationships consistently.
4. Expand high-signal Terraform and Kubernetes relationships without inferring unsupported entities.
