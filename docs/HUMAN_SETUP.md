# Human Setup Guide

This project can generate three output styles:
- Graph JSON + Mermaid source (always available)
- Mermaid-rendered image files (`.svg` / `.png`) via native Mermaid CLI, Docker, or Podman
- Non-Mermaid architecture images (`.diagram.svg/.png/.pdf`) via `python-diagrams` + Graphviz

## 1. Base Prerequisites

Required:
- `uv`
- Python 3.10+

Optional by feature:
- native `mmdc`, Docker, or Podman for `--svg` / `--png` Mermaid image rendering
- Graphviz system package (`dot`) for `--diagram-format ...`
- `boto3` Python dependency for `aws-boto3` mode

## 2. Install Project

```bash
uv sync
```

Optional Python dependency for non-Mermaid rendering:

```bash
uv add diagrams
```

Optional Python dependencies for richer AWS discovery mode:

```bash
uv add boto3 diagrams
# or:
uv sync --extra aws-boto3
```

## 3. Verify Toolchain

Base CLI:

```bash
uv run diagram-gen --help
uv run diagram-gen spec --help
uv run diagram-gen spec-batch --help
```

Mermaid rendering (one option is sufficient):

```bash
command -v mmdc
docker --version
podman --version
```

For a fully provisioned image that avoids host installs, see [CONTAINERS.md](CONTAINERS.md).

Graphviz rendering:

```bash
dot -V
```

## 4. Common Commands

Generate baseline outputs (`.graph.json` + `.mmd`):

```bash
uv run diagram-gen --discover --root infra --out-dir output --name snapshot
```

Generate Mermaid image outputs:

```bash
uv run diagram-gen --discover --root infra --out-dir output --name snapshot --svg --png
```

Generate non-Mermaid image outputs:

```bash
uv run diagram-gen --discover --root infra --out-dir output --name snapshot --diagram-format svg --diagram-format png
```

Search the installed branded/technology icon catalog:

```bash
uv run --extra render diagram-gen icons --search cloudflare
uv run --extra render diagram-gen icons --search supabase
uv run --extra render diagram-gen icons --provider programming
```

See [ICONS.md](ICONS.md) for canonical icon names, explicit JSON/YAML icon
selection, automatic filename-language matching, and Mermaid limitations.

Group artifacts into `output/<name>/` and zip bundle:

```bash
uv run diagram-gen --discover --root infra --out-dir output --name snapshot --artifact-folder --zip-artifacts
```

Render from a YAML/JSON architecture spec:

```bash
uv run diagram-gen spec --spec examples/spec-architecture.yaml --check
uv run diagram-gen spec --spec examples/spec-architecture.yaml \
  --output architecture --format svg --format png
```

Validate or render a directory of authored specs:

```bash
uv run diagram-gen spec-batch --spec-dir specs --check
uv run diagram-gen spec-batch --spec-dir specs --out-dir output \
  --format svg --format png
```

Compare current/future architecture states:

```bash
uv run diagram-gen compare --spec specs/migration.yaml --output-prefix migration --format png
```

Generate a live K8s namespace diagram and export generated spec:

```bash
uv run diagram-gen k8s discover --namespace posit-workbench --output wb-live --export-spec wb-live.yaml
```

Generate a richer AWS live diagram via boto3 discovery:

```bash
uv add boto3 diagrams
uv run diagram-gen aws-boto3 --profile <aws-profile> --region us-east-1 --output aws-live --format png --export-json aws-live.json
```

## 5. Running Tests

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

## 6. Blind Spots

When a collector fails (e.g. missing AWS credentials, kubectl not found), the CLI captures the error and emits blind spots reports alongside other artifacts:
- `<name>.blindspots.json` — machine-readable
- `<name>.blindspots.md` — human-readable

Check these files to understand what the tool could not discover.

## 7. Troubleshooting

`Mermaid image render command failed`:
- Ensure native `mmdc` works, or that Docker/Podman is running and image pull is allowed.
- Force a specific engine with `--mermaid-runtime container --container-engine podman` (or `docker`).
- Override image if needed: `--mermaid-image <image>`.

`podman compose` reports that no provider is installed:
- Compose is not required by this project; use the documented `podman build` and `podman run` commands.
- If a separate workflow needs Compose, install `podman-compose` or `docker-compose`.

Non-Mermaid rendering says `No module named 'diagrams'`:
- Run `uv add diagrams`.

Non-Mermaid rendering fails because `dot` is missing:
- Install Graphviz and confirm with `dot -V`.

SVG icons appear broken on another machine:
- Use current CLI outputs. Non-Mermaid SVG icons are now embedded as data URIs.
