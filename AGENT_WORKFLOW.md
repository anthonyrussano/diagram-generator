# Agent Workflow: Diagram Generation

## 1. Establish Context

1. Confirm repository root.
2. Confirm tool availability: `uv`, `aws`, `kubectl`, `helm`, `git`.
3. Run `uv sync` before any generation or validation.
4. Confirm AWS identity when using AWS scan:
   - `aws --profile <profile> --region <region> sts get-caller-identity`

## 2. Preflight by Requested Output

For Mermaid image output (`--svg` / `--png`), check for a native renderer or container engine:

```bash
command -v mmdc
docker --version
podman --version
```

Only one Mermaid runtime is required. `podman compose` is not required.

For non-Mermaid output (`--diagram-format ...`):

```bash
dot -V
uv run --with diagrams python -c 'from importlib.metadata import version; print(version("diagrams"))'
```

For authored specs, validate the full set before rendering:

```bash
uv run diagram-gen spec-batch --spec-dir <spec-dir> --check
```

## 3. Choose Data Sources

Use one or more:
- `aws` for live AWS inventory
- `terraform` for `.tfstate` and `.tf.json`
- `json` for existing graph-like JSON
- `kubernetes` for manifests and optionally live cluster
- `helm` charts via `--helm-chart` (rendered through `helm template`)

## 4. Execute Collection

Preferred command pattern:

```bash
uv run diagram-gen \
  --discover \
  --root <input-root> \
  --source aws \
  --profile <profile> \
  --region <region> \
  --out-dir output \
  --name <diagram-name>
```

Keep `<input-root>` scoped to infrastructure inputs and outside `--out-dir` so discovery cannot ingest artifacts from prior runs.

Optional output flags:

```bash
--svg --png
--diagram-format svg --diagram-format png
--artifact-folder --zip-artifacts
```

## 5. Validate Output Quality

Run required checks:

```bash
uv run python -m py_compile src/agent_diagrams/*.py src/agent_diagrams/renderers/*.py
uv run diagram-gen --help
```

Then run at least one smoke command:

```bash
uv run diagram-gen --source json --json <input.json> --out-dir output --name smoke
```

Validate:
1. Output files exist.
2. Node/edge count is printed.
3. `.graph.json` has no duplicate node IDs.
4. Requested output mode files exist (`.svg/.png/.diagram.<fmt>/.zip`).

For multiple authored specs, use `spec-batch` with repeated `--format` flags. Review its aggregate counts and inspect the rendered images at full resolution; Graphviz success alone does not prove that edge routing is readable.

## 6. Produce Final Artifacts

Always report:
- Mermaid source path
- Graph JSON path
- Image path(s) when requested
- Zip path when requested
- Summary of sources, counts, and notable gaps

## 7. Common Gaps to Report

- Insufficient IAM permissions for some AWS APIs
- Kubernetes context not configured
- Terraform resources missing when only modules are present without state/json
- Helm render failures (invalid chart, missing values, or bad templates)
- Native Mermaid CLI, Docker, and Podman all unavailable when Mermaid image generation is requested
- `python-diagrams`/Graphviz unavailable when non-Mermaid rendering is requested
