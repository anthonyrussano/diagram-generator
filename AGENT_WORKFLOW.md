# Agent Workflow: Diagram Generation

## 1. Establish Context

1. Confirm repository root.
2. Confirm Docker or Podman is available.
3. Run `./scripts/build-container.sh` before generation or validation. It uses
   the layer cache and injects the approved sibling-repository CAs when present.
4. Use `./scripts/run-container.sh` for all `diagram-gen` commands by default.
   Host-side `uv` is a fallback or fast inner loop, not final verification.
5. Confirm AWS identity when using AWS scan:
   - Mount the required AWS configuration as described in `docs/CONTAINERS.md`.
   - Run `aws sts get-caller-identity` in the selected container context before collection.

## 2. Preflight by Requested Output

For Mermaid image output (`--svg` / `--png`), smoke the native renderer included
in the image:

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name preflight-mermaid --svg --png
```

No host Mermaid CLI, browser, Compose service, or mounted container socket is required.

For non-Mermaid output (`--diagram-format ...`), smoke the bundled Graphviz runtime:

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name preflight-graphviz --diagram-format svg
```

For authored specs, validate the full set before rendering:

```bash
./scripts/run-container.sh spec-batch --spec-dir <spec-dir> --check
```

### Review-ready output presets

Use the bundled review preset when publishing an infrastructure diagram into a
wiki, a PR, or an agent session recap:

```bash
./scripts/run-container.sh --source json --json <input.graph.json> \
  --out-dir output --name review --review-bundle
```

The preset requests Graphviz SVG/PNG previews and an editable draw.io scene,
with the original graph JSON, Mermaid source, and a ZIP. Inspect the previews
before delivering, and check the graph/blind-spot JSON before sharing the ZIP.
The Mermaid source is an alternative representation, not a layout-exact copy
of the Graphviz visuals.

For a purely conceptual Mermaid diagram, avoid running inventory collectors:

```bash
./scripts/run-container.sh mermaid --input examples/mermaid-flow.mmd \
  --out-dir output --output concept
```

This produces an `.mmd` source and SVG/PNG previews. It does not generate graph
JSON, draw.io, or Excalidraw. Invalid Mermaid must be repaired before delivery.
See [the gstack workflow comparison](docs/GSTACK_DIAGRAM_COMPARISON.md).

## 3. Choose Data Sources

Use one or more:
- `aws` for live AWS inventory
- `terraform` for `.tf`, `.tfstate`, `.tf.json`, and module directories
- `json` for existing graph-like JSON
- `kubernetes` for manifests and optionally live cluster
- `helm` charts via `--helm-chart` (rendered through `helm template`)

## 4. Execute Collection

Preferred command pattern:

```bash
./scripts/run-container.sh \
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
./scripts/check-container.sh
```

Then run at least one smoke command:

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name smoke
```

Validate:
1. Output files exist.
2. Node/edge count is printed.
3. `.graph.json` has no duplicate node IDs.
4. Requested output mode files exist (`.svg/.png/.diagram.<fmt>/.zip`).

For multiple authored specs, use `spec-batch` with repeated `--format` flags. Review its aggregate counts and inspect the rendered images at full resolution; Graphviz success alone does not prove that edge routing is readable.

## 6. Produce Final Artifacts

Always report:
- Canonical source path (Mermaid `.mmd`, a graph `.graph.json`, or a YAML/JSON spec)
- Rendered SVG/PNG paths, after visually checking legibility
- Native editable `.drawio` path, if generated
- ZIP path when requested, after reviewing included metadata
- Summary of sources, node/edge counts where available, and notable gaps

For `diagram-gen mermaid`, report the `.mmd` and images; that mode has no
graph JSON or native editable scene.

## 7. Common Gaps to Report

For HCL, richer manifest relationships, editable draw.io exports, and trusted
Python authoring, follow [docs/AUTHORING_AND_EXPORT.md](docs/AUTHORING_AND_EXPORT.md).

- Insufficient IAM permissions for some AWS APIs
- Kubernetes context not configured
- Terraform resources missing when only modules are present without state/json
- Helm render failures (invalid chart, missing values, or bad templates)
- Native Mermaid CLI, Docker, and Podman all unavailable when Mermaid image generation is requested
- `python-diagrams`/Graphviz unavailable when non-Mermaid rendering is requested
