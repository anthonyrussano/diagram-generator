# Agent Diagrams Repo

This repository is structured so autonomous agents and human operators can reliably generate infrastructure diagrams from:
- AWS account inventory (via `aws` CLI)
- Existing JSON graph files
- Terraform HCL, state, and JSON config (`.tf`, `.tfstate`, `.tf.json`)
- Kubernetes manifests and optionally live cluster resources (`kubectl`)
- Helm charts (rendered via `helm template`)
- Spec-authored architectures (`.yaml` / `.json`) and current-vs-future comparisons
- Trusted Python scripts using the full Diagrams DSL (loops, helpers, custom nodes)

## Design Goals

- Agent-first: one CLI entrypoint with deterministic outputs.
- Source-agnostic: normalize all sources into one graph model.
- Output for humans and agents: graph JSON, Mermaid source, and optional image renders.
- Infrastructure collection is read-only; Python authoring executes trusted code with the runtime user's permissions.

## Setup

Detailed setup docs:
- Humans: [docs/HUMAN_SETUP.md](docs/HUMAN_SETUP.md)
- Agents: [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md)
- Containers (Podman, Docker, and GHCR): [docs/CONTAINERS.md](docs/CONTAINERS.md)
- Node icon catalog and resolution: [docs/ICONS.md](docs/ICONS.md)
- Architecture spec validation, batch rendering, and layout controls: [docs/SPECS.md](docs/SPECS.md)
- HCL, manifest relationships, Python authoring, and editable draw.io output: [docs/AUTHORING_AND_EXPORT.md](docs/AUTHORING_AND_EXPORT.md)

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
uv run diagram-gen --discover --root infra --out-dir output --name account-snapshot
```

Keep the discovery root scoped to infrastructure inputs and separate from the output directory. Replace `infra` with the folder containing the JSON, Terraform, or Kubernetes files to scan.

Generate Mermaid image files with automatic native/Docker/Podman detection:

```bash
uv run diagram-gen --discover --root infra --out-dir output --name account-snapshot --svg --png
```

Force rootless Podman for Mermaid rendering:

```bash
uv run diagram-gen --discover --root infra --out-dir output --name account-snapshot \
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
uv run diagram-gen --discover --root infra --out-dir output --name account-snapshot --diagram-format svg --diagram-format png
```

Search more than 2,600 available technology and service icons:

```bash
uv run --extra render diagram-gen icons --search cloudflare
uv run --extra render diagram-gen icons --search supabase
uv run --extra render diagram-gen icons --provider programming
```

Non-Mermaid renders infer branded icons from node kinds, labels, file
extensions, and explicit `attrs.icon` values. Unknown kinds are reported and
rendered blank instead of being silently represented by an unrelated icon. See
[docs/ICONS.md](docs/ICONS.md) for canonical names and JSON/YAML examples.

Write artifacts into dedicated folder and zip:

```bash
uv run diagram-gen --discover --root infra --out-dir output --name account-snapshot --artifact-folder --zip-artifacts
```

Render from a hand-authored YAML/JSON architecture spec:

```bash
uv run diagram-gen spec --spec examples/spec-architecture.yaml --check
uv run diagram-gen spec --spec examples/spec-architecture.yaml \
  --output architecture --format svg --format png
```

Parse Terraform HCL and export editable draw.io alongside an image:

```bash
./scripts/run-container.sh --source terraform --terraform examples/terraform-hcl \
  --name terraform-example --diagram-format svg --diagram-format drawio
```

Render a trusted Python Diagrams script with loops and helper functions:

```bash
./scripts/run-container.sh python --script examples/python-architecture.py \
  --output python-example --format png --format drawio
```

Use `--format drawio` for spec, batch, comparison, and live workflows. See
[the authoring/export guide](docs/AUTHORING_AND_EXPORT.md) for Kubernetes
relationship coverage, editable export behavior, and Python execution details.

Validate or render a directory of specs in one deterministic batch:

```bash
uv run diagram-gen spec-batch --spec-dir specs --check
uv run diagram-gen spec-batch --spec-dir specs --out-dir output \
  --format svg --format png
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
- `output/<name>.diagram.drawio`: editable diagram (`--diagram-format drawio`), with a `.dot` intermediate
- `output/<name>/...`: optional artifact folder (`--artifact-folder`)
- `output/<name>.blindspots.json`: blind spots report when collector errors occur
- `output/<name>.blindspots.md`: blind spots report (Markdown)
- `output/<name>.zip`: optional zip bundle (`--zip-artifacts`)
- `output/<output>.<fmt>`: spec-driven rendered diagram (`diagram-gen spec`)
- `output/<output>.<fmt>`: Python-authored diagram (`diagram-gen python`; additional diagrams use `-2`, `-3`, etc.)
- `output/<relative-spec-path>.<fmt>`: deterministic multi-spec output (`diagram-gen spec-batch`)
- `output/<prefix>_current.<fmt>`, `output/<prefix>_future.<fmt>`, `output/<prefix>_diff.md`, `output/<prefix>_diff.json` (`diagram-gen compare`)
- `output/<output>.<fmt>` plus optional exported spec (`diagram-gen k8s discover|annotate`)
- `output/<output>.graph.json`, `output/<output>.mmd`, `output/<output>.blindspots.json` (`diagram-gen aws-boto3`)

## Running Tests

```bash
uv sync --extra dev --extra render
uv run pytest tests/ -v
```

## Agent Workflow

See [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) for execution workflow and quality checks.

### Prompting an agent during an investigation or build

You can introduce this repository mid-session. Give the agent a short brief defining
what the diagram should explain, its audience, and whether it represents observed
reality, a proposed design, or a comparison. Ask it to read this repository's
instructions before using the generator.

Useful prompting habits:

1. **Distinguish current, proposed, and uncertain.** Use the latest findings rather
   than superseded hypotheses. During builds, distinguish implemented components
   from planned ones. Configuration declarations are not proof of runtime state.
2. **Give each diagram one main question.** “Show how requests reach the application”
   is a clearer brief than “diagram everything.” Topology, authentication,
   deployment, and failure recovery often deserve separate diagrams.
3. **Make arrows mean something explicit.** Terraform dependencies, network
   connections, ownership, and data flow are different relationships. Request
   meaningful labels and a legend when styles distinguish relationship types,
   uncertainty, or planned state.
4. **Keep editable source alongside the images.** Save the YAML/JSON spec or Python
   script and brief notes linking important claims to files, commands, or design
   decisions. Keep durable inputs outside disposable build folders. This helps
   later sessions resume without repeating discovery. [Official OpenAI guidance](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)
   likewise recommends preserving material context with evidence references.
5. **Require visual inspection.** A successful render confirms file generation.
   Ask the agent to open the PNG, check labels and arrow routing, and revise anything
   confusing before delivering it.

For session-based diagrams, prefer **YAML specs**: they are easy to review and adjust
as understanding changes. Use **collectors** for infrastructure extracted from HCL,
manifests, or live inventory; use **Python** when helpers, loops, or custom
composition materially simplify the diagram. The agent can choose the appropriate
mode under that guidance. Use `compare` for explicit current/future views.

Reusable request:

> Use `~/Projects/diagram-generator` to diagram **[the system or flow]** based on
> our latest findings and decisions in this session.
>
> Read its `AGENTS.md`, `AGENT_WORKFLOW.md`, and relevant authoring documentation first.
>
> The diagram should explain **[the main question]** for **[the intended audience]**.
> Represent **[current state / proposed design / current versus proposed]**.
> Distinguish confirmed facts, inferences, and planned components, and flag anything
> unresolved.
>
> Prefer a YAML spec unless another supported workflow is more suitable. Save the
> source and brief evidence/assumption notes alongside PNG, SVG, and draw.io outputs
> under **[destination]**.
>
> Follow the container workflow. Label relationships clearly, inspect the rendered
> PNG, and fix readability issues before finishing. Report the files produced and
> any meaningful limitations.

The expanded [agent prompt template](prompts/diagram_agent_prompt.md) includes
execution guidance and command examples for the supported authoring paths.

Two practical details afterward:

- **Regenerate from the saved source.** Manual draw.io edits do not flow back into
  YAML, JSON, or Python. Keep manually edited versions clearly named.
- **Review bundles before sharing.** Collector graph JSON can contain raw
  infrastructure attributes, including values absent from the visible diagram.

## Agent Contribution Rules

See [AGENTS.md](AGENTS.md) for coding and verification requirements.

## Feature Research

See [FEATURE_OPPORTUNITIES.md](docs/FEATURE_OPPORTUNITIES.md) for the source review
of Ansible Playbook Grapher, Ansible Inventory Grapher, and TerraVision. It records
potential collectors and presentation improvements, their integration tradeoffs,
and a suggested implementation order. These are proposals rather than supported
CLI features.
