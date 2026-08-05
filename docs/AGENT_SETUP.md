# Agent Setup Guide

This guide is for autonomous/semi-autonomous runs of `diagram-gen`.

## Default execution environment

Agents must use the repository container by default. From the repository root:

```bash
./scripts/build-container.sh
./scripts/run-container.sh --help
```

The build wrapper prefers Docker, falls back to Podman, and automatically uses
the approved CHOP and Netskope CA files from the sibling `helm-charts` checkout
when they exist. The run wrapper mounts this repository at `/workspace` and
preserves host ownership for generated artifacts. Set `CONTAINER_ENGINE` to
select an engine or `DIAGRAM_GEN_IMAGE` to override the image tag.

Host-side `uv run ...` is allowed for quick development feedback only. If the
container cannot be used, record the reason and report host execution as a
validation blind spot.

## 1. Preflight Checks

Run from repo root:

```bash
pwd
./scripts/run-container.sh --help
./scripts/run-container.sh spec --help
./scripts/run-container.sh spec-batch --help
./scripts/run-container.sh aws-boto3 --help
```

If Mermaid image output is requested (`--svg` / `--png`):

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name preflight-mermaid --svg --png
```

The repository container includes the native Mermaid runtime. Compose and a mounted container socket are not required; see [CONTAINERS.md](CONTAINERS.md).

If non-Mermaid output is requested (`--diagram-format ...`):

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name preflight-graphviz --diagram-format svg
```

If `aws-boto3` mode is requested:

```bash
./scripts/run-container.sh aws-boto3 --help
```

## 2. Required Validation Before Finishing

Always run:

```bash
./scripts/check-container.sh
```

And at least one smoke run:

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name smoke
```

Verify:
- Output files exist.
- Node/edge counts are printed.

If composite workflows were changed, smoke at least one:

```bash
./scripts/run-container.sh spec --spec <spec.yaml> --check
./scripts/run-container.sh spec --spec <spec.yaml> --output smoke-spec --format png
./scripts/run-container.sh spec-batch --spec-dir <spec-dir> --check
./scripts/run-container.sh compare --spec <states.yaml> --output-prefix smoke-compare --format png
./scripts/run-container.sh aws-boto3 --help
```

For a documentation set, prefer one batch invocation with repeated `--format` flags over shell loops. It loads each spec once, preserves relative paths, and prints per-spec plus aggregate counts. See [SPECS.md](SPECS.md).

## 3. Feature-Specific Smoke Commands

Mermaid image smoke:

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name smoke-mermaid --svg --png
```

Non-Mermaid smoke (bundled Graphviz runtime):

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name smoke-diagram --diagram-format svg --diagram-format png
```

Artifact packaging smoke:

```bash
./scripts/run-container.sh --source json --json <input.json> --out-dir output --name smoke-bundle --artifact-folder --zip-artifacts
```

## 4. Blind Spots Reporting

When collector errors occur, `.blindspots.json` and `.blindspots.md` artifacts are emitted alongside other outputs. These report:
- Collection errors (API failures, missing credentials)
- Empty sources (sources that returned no resources)
- Unqueryable resources and permission denials

## 5. Reporting Requirements

When finishing, include:
- sources scanned
- commands run
- output files produced
- node/edge counts
- blind spots (check `.blindspots.json` if present)
- limitations (permissions, missing dependencies, failed tools)
