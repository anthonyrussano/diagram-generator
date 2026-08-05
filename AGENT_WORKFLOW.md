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
