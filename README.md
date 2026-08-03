# Agent Diagrams Repo

This repository is structured so autonomous agents and human operators can reliably generate infrastructure diagrams from:
- AWS account inventory (via `aws` CLI)
- Existing JSON graph files
- Terraform state/config (`.tfstate`, `.tf.json`)
- Kubernetes manifests and optionally live cluster resources (`kubectl`)
- Helm charts (rendered via `helm template`)
- Spec-authored architectures (`.yaml` / `.json`) and current-vs-future comparisons

## Design Goals

- Agent-first: one CLI entrypoint with deterministic outputs.
- Source-agnostic: normalize all sources into one graph model.
- Output for humans and agents: graph JSON, Mermaid source, and optional image renders.
- Non-destructive: scans and reads only.

## Setup

Detailed setup docs:
- Humans: [docs/HUMAN_SETUP.md](docs/HUMAN_SETUP.md)
- Agents: [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md)
- Containers (Podman, Docker, and GHCR): [docs/CONTAINERS.md](docs/CONTAINERS.md)

Quick setup:

```bash
uv sync
```

Optional dependency for non-Mermaid rendering:

```bash
uv add diagrams
```

Optional dependency for richer boto3 AWS discovery mode:

```bash
uv add boto3 diagrams
# or from project extras:
uv sync --extra aws-boto3
```

## Prerequisites

Base:
- `uv`
- Python 3.10+

Optional by feature:
- native `mmdc`, Docker, or Podman for Mermaid image rendering (`--svg` / `--png`)
- Graphviz (`dot`) + `python-diagrams` for non-Mermaid outputs (`--diagram-format`)
- `boto3`/`botocore` for `diagram-gen aws-boto3`

## Quick Start

Discover local files and build baseline artifacts:

```bash
uv run diagram-gen --discover --root . --out-dir output --name account-snapshot
```

Generate Mermaid image files with automatic native/Docker/Podman detection:

```bash
uv run diagram-gen --discover --out-dir output --name account-snapshot --svg --png
```

Force rootless Podman for Mermaid rendering:

```bash
uv run diagram-gen --discover --out-dir output --name account-snapshot \
  --svg --png --mermaid-runtime container --container-engine podman
```

Run the fully provisioned project container without installing AWS CLI, kubectl, Helm, Graphviz, or Mermaid CLI on the host:

```bash
podman build --file Containerfile --tag diagram-gen:local .
podman run --rm --userns=keep-id --volume "$PWD:/workspace:Z" \
  diagram-gen:local --source json --json tests/snapshots/simple_graph.graph.json \
  --out-dir output --name container-smoke --svg --png \
  --diagram-format svg --diagram-format png
```

Generate non-Mermaid architecture images:

```bash
uv run diagram-gen --discover --out-dir output --name account-snapshot --diagram-format svg --diagram-format png
```

Write artifacts into dedicated folder and zip:

```bash
uv run diagram-gen --discover --out-dir output --name account-snapshot --artifact-folder --zip-artifacts
```

Render from a hand-authored YAML/JSON architecture spec:

```bash
uv run diagram-gen spec --spec specs/architecture.yaml --output architecture --format png
```

Render current/future states and write a diff summary:

```bash
uv run diagram-gen compare --spec specs/migration.yaml --output-prefix migration --format png
```

Discover a live Kubernetes namespace into a spec and diagram:

```bash
uv run diagram-gen k8s discover --namespace posit-workbench --output wb-live --export-spec wb-live.yaml
```

Render a richer AWS account diagram using boto3 discovery:

```bash
uv run diagram-gen aws-boto3 --profile <aws-profile> --region us-east-1 --output aws-live --format png --export-json aws-live.json
```

## Outputs

- `output/<name>.graph.json`: canonical graph for downstream automation/review
- `output/<name>.mmd`: Mermaid diagram source
- `output/<name>.svg`: Mermaid SVG (`--svg`)
- `output/<name>.png`: Mermaid PNG (`--png`)
- `output/<name>.diagram.<fmt>`: non-Mermaid output (`--diagram-format`, repeatable)
- `output/<name>/...`: optional artifact folder (`--artifact-folder`)
- `output/<name>.blindspots.json`: blind spots report when collector errors occur
- `output/<name>.blindspots.md`: blind spots report (Markdown)
- `output/<name>.zip`: optional zip bundle (`--zip-artifacts`)
- `output/<output>.<fmt>`: spec-driven rendered diagram (`diagram-gen spec`)
- `output/<prefix>_current.<fmt>`, `output/<prefix>_future.<fmt>`, `output/<prefix>_diff.md`, `output/<prefix>_diff.json` (`diagram-gen compare`)
- `output/<output>.<fmt>` plus optional exported spec (`diagram-gen k8s discover|annotate`)
- `output/<output>.graph.json`, `output/<output>.mmd`, `output/<output>.blindspots.json` (`diagram-gen aws-boto3`)

## Running Tests

```bash
uv sync --extra dev
uv run pytest tests/ -v
```

## Agent Workflow

See [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) for execution workflow and quality checks.

## Agent Contribution Rules

See [AGENTS.md](AGENTS.md) for coding and verification requirements.
