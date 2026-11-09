---
name: diagram-generator
description: Create and verify evidence-backed infrastructure diagrams or simple Mermaid flowcharts; preserve editable sources and render preview artifacts for review.
---

# Diagram generator: source first, render before delivery

Use this skill for architecture diagrams, infrastructure topology, migration flows, and
small process diagrams. Its working CLI is `diagram-gen` in this repository.
Read `AGENTS.md`, `AGENT_WORKFLOW.md`, and relevant `docs/` guides before executing.

## 1. Define the diagram

- Name the **one question** the diagram answers and its audience.
- Identify the authoritative inputs: spec, graph JSON, Terraform, Kubernetes, AWS,
  or an explicitly user-supplied Mermaid flow.
- Mark whether facts are **observed**, **declared**, **inferred**, or **proposed**.
  A Terraform declaration or a generated example is not evidence of live runtime state.
- Keep labels short, and annotate relationship semantics. Prefer several focused
  diagrams over an unreadable all-in-one view (roughly 5-15 nodes per narrative view).
- Do not invent nodes or edges to fill a gap. Preserve collector blind-spot reports.

## 2. Choose the workflow

**Infrastructure source / graph input — default choice.** Use the review bundle,
which produces graph JSON, Mermaid, Graphviz SVG/PNG previews, a native editable
draw.io scene, a Ferroprint project JSON, and a ZIP in one output folder:

```bash
./scripts/build-container.sh
./scripts/run-container.sh --source json --json input.graph.json \
  --out-dir output --name architecture --review-bundle
```

Change the source flags for scoped Terraform/Kubernetes/AWS inputs. Scope discovery
outside the output directory. The SVG/PNG are Graphviz previews of the same graph
as the draw.io export; the `.mmd` is an alternative Mermaid representation.\nThe `.ferroprint.json` is a separate editable browser-document format, not a\nGraphviz-layout-exact copy.

**YAML/JSON authoring** (preferred for diagrams created during a session):

```bash
./scripts/run-container.sh spec --spec architecture.yaml --check
./scripts/run-container.sh spec --spec architecture.yaml \
  --output architecture --format svg --format png --format drawio
```

Save `architecture.yaml` alongside the outputs: it is the editable source of
truth. The `.drawio` is a separate, manually editable presentation.

**Conceptual flow or user-authored Mermaid**, with no live collector needed:

```bash
./scripts/run-container.sh mermaid --input flow.mmd \
  --out-dir output --output flow
```

This stages and verifies SVG and PNG before publishing a normalized `.mmd`.
Markdown input with a fenced Mermaid block also works. The Mermaid path does
**not** create a draw.io or Excalidraw scene: do not claim otherwise.

**Model-checked state machines** (provisioning, retries, protocols, failover):
`diagram-gen statechart --spec MODEL.tla --config MODEL.cfg --view view.mjs
--out output/model --render svg`. Read the isolated setup guide under
`integrations/statechart/` first. Exit code 1 means a *rule was violated*;
preserve its counterexample report. Do not weaken a model rule to get exit 0.
Label counterexamples **model only** until they are reproduced in the real system.

## 3. Validate before sharing

1. Run the repository container checks: `./scripts/check-container.sh`.
2. Confirm every requested file exists, is nonempty, and corresponds to the
   current input. A renderer's nonzero exit is not a completed diagram.
3. Open the SVG/PNG and inspect legibility, spacing, edge direction, truncation,
   layering, icon accuracy, and explanatory labels. Revise the source and rerender.
4. Review `*.blindspots.json` / `*.blindspots.md`, unresolved icon notices,
   and collector warnings. State their impact; do not quietly omit them.
5. Check ZIP contents before attaching or publishing. Raw graph JSON and source
   metadata can disclose configuration, identifiers, or infrastructure details.
6. Publish the source/spec, image previews, and editable output together. Give
   precise paths and distinguish editable draw.io/Ferroprint documents from generated images.

## 4. Editing and provenance

- A regenerated preview must come from the latest source, not an earlier image.
- Changes made manually in draw.io do **not** propagate into Mermaid or YAML.
  Keep an edited copy separately if it must survive regeneration.
- To review a live system, never pass off static source analysis as measured status.
- Excalidraw is not currently a native export format; gstack's
  [diagram skill](https://github.com/garrytan/gstack/blob/main/diagram/SKILL.md)
  is a separate browser-bundle workflow, not a dependency of this repository.
- For PDF documentation, prefer source-embedded Mermaid or SVG as appropriate
  rather than downscaling a raster image.

## 5. Delivery report

Report: the question addressed, evidence/source type and date, observed vs
proposed status, node/edge counts if provided by the CLI, all artifact paths,
which file is editable, the rendering checks performed, and remaining blind spots.
If an image cannot be rendered or inspected, report the limitation and do not
call the bundle complete.
