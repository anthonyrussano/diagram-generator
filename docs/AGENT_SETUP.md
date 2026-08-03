# Agent Setup Guide

This guide is for autonomous/semi-autonomous runs of `diagram-gen`.

## 1. Preflight Checks

Run from repo root:

```bash
pwd
uv run diagram-gen --help
uv run diagram-gen spec --help
uv run diagram-gen aws-boto3 --help
```

If Mermaid image output is requested (`--svg` / `--png`):

```bash
command -v mmdc
docker --version
podman --version
```

Only one Mermaid runtime is required. Prefer the repository container when external tools are unavailable; see [CONTAINERS.md](CONTAINERS.md). Compose is not required.

If non-Mermaid output is requested (`--diagram-format ...`):

```bash
dot -V
uv run --with diagrams python -c "import diagrams; print(diagrams.__version__)"
```

If `aws-boto3` mode is requested:

```bash
uv sync --extra aws-boto3
```

## 2. Required Validation Before Finishing

Always run:

```bash
uv run pytest tests/ -v
uv run python -m py_compile src/agent_diagrams/*.py src/agent_diagrams/renderers/*.py
uv run diagram-gen --help
```

And at least one smoke run:

```bash
uv run diagram-gen --source json --json <input.json> --out-dir output --name smoke
```

Verify:
- Output files exist.
- Node/edge counts are printed.

If composite workflows were changed, smoke at least one:

```bash
uv run diagram-gen spec --spec <spec.yaml> --output smoke-spec --format png
uv run diagram-gen compare --spec <states.yaml> --output-prefix smoke-compare --format png
uv run diagram-gen aws-boto3 --help
```

## 3. Feature-Specific Smoke Commands

Mermaid image smoke:

```bash
uv run diagram-gen --source json --json <input.json> --out-dir output --name smoke-mermaid --svg --png
```

Non-Mermaid smoke (ephemeral dependency install):

```bash
uv run --with diagrams diagram-gen --source json --json <input.json> --out-dir output --name smoke-diagram --diagram-format svg --diagram-format png
```

Artifact packaging smoke:

```bash
uv run diagram-gen --source json --json <input.json> --out-dir output --name smoke-bundle --artifact-folder --zip-artifacts
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
