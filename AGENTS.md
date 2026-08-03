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

1. `uv run pytest tests/ -v` (all tests must pass)
2. `uv run python -m py_compile src/agent_diagrams/*.py src/agent_diagrams/renderers/*.py`
3. `uv run diagram-gen --help`
4. At least one smoke run of `uv run diagram-gen` with selected sources.
5. Verify output files exist and node/edge counts are printed.

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
