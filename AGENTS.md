# AGENTS.md

This repository is intended for autonomous or semi-autonomous coding agents.

## Mission

Improve `diagram-gen` so infrastructure diagrams are accurate, reproducible, and easy to review in PRs.

## Ground Rules

1. Preserve deterministic behavior.
2. Prefer additive changes over broad rewrites.
3. Keep source collectors independent (`aws`, `terraform`, `json`, `kubernetes`).
4. Never invent infrastructure entities or relationships.
5. Report data collection blind spots explicitly.

## Container-First Execution Policy

The repository container is the default execution environment for agents. Use
it for setup, diagram generation, Graphviz/Mermaid rendering, smoke tests, and
final validation. Host-side `uv run ...` commands are permitted for a fast
inner loop, but they do not replace the required container verification.

1. Build or refresh the image before generation and final checks:
   `./scripts/build-container.sh`
2. Run `diagram-gen` through the mounted-workspace wrapper:
   `./scripts/run-container.sh <diagram-gen arguments>`
3. On this workspace layout, the build wrapper automatically injects the CHOP
   and Netskope roots from `../helm-charts/network-diagnostics/image/` when
   present. Override with `DIAGRAM_GEN_CHOP_CA` and
   `DIAGRAM_GEN_NETSKOPE_CA` only when the approved certificates live elsewhere.
4. The wrappers prefer Docker and fall back to Podman. Set
   `CONTAINER_ENGINE=podman` or `CONTAINER_ENGINE=docker` to select explicitly.
5. Fall back to host execution only when the container engine is unavailable or
   the container path fails for a documented reason. Report that fallback and
   the exact failure as a blind spot.

## Repo Layout

- `src/agent_diagrams/cli.py`: orchestration, argument surface, and composite command dispatch
- `src/agent_diagrams/collectors.py`: data collection adapters (aws cli, terraform, json, k8s, helm)
- `src/agent_diagrams/model.py`: graph contracts (Node, Edge, GraphData)
- `src/agent_diagrams/normalize.py`: dedupe/normalization
- `src/agent_diagrams/blind_spots.py`: blind spots report generation (JSON + Markdown)
- `src/agent_diagrams/spec_workflows.py`: spec rendering, validation, and current/future comparison
- `docs/SPECS.md`: authored-spec schema, batch workflow, and Graphviz layout controls
- `src/agent_diagrams/live_k8s.py`: live Kubernetes discovery, annotation, and status inference
- `src/agent_diagrams/aws_boto3_mode.py`: rich AWS boto3 discovery, diagram generation, and GraphData conversion
- `src/agent_diagrams/renderers/`: output renderers (json, mermaid, diagrams, images)
- `tests/`: pytest test suite with snapshot golden files
- `scripts/`: container-first build, validation, and runtime wrappers for agents
- `prompts/`: reusable execution prompt templates
- `AGENT_WORKFLOW.md`: operator runbook
- `docs/AGENT_SETUP.md`: explicit setup and validation commands for agents
- `docs/HUMAN_SETUP.md`: explicit setup and usage commands for human operators

## Contribution Priorities

1. Increase source coverage with high-signal relationships.
2. Improve robustness of collectors under partial permissions/failures.
3. Add output formats useful for PR review and docs publication.
4. Keep command interface stable; if changed, update docs in same PR.

## Required Checks Before Finishing

1. `./scripts/build-container.sh`
2. `./scripts/check-container.sh` (tests, compilation, and CLI help must pass)
3. At least one smoke run of `./scripts/run-container.sh` with selected sources.
4. Verify output files exist and node/edge counts are printed.

When feature flags are requested, validate them too:
- Mermaid images: smoke with `--svg --png`.
- Non-Mermaid render: smoke with `--diagram-format svg --diagram-format png`.
- Bundling: smoke with `--artifact-folder --zip-artifacts`.

## Implementation Guidelines

- Keep functions small and source-specific.
- Add fields to metadata when behavior changes materially.
- Use explicit IDs and stable edge relationships.
- Treat subprocess failures as actionable errors with clear command context.

## PR Checklist for Agents

1. What source(s) were changed and why?
2. What new node/edge kinds were introduced?
3. What command(s) were run for verification?
4. What limitations remain?
