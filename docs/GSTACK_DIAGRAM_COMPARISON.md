# gstack /diagram review and applicability to diagram-generator

Reviewed 2026-11-08. Upstream:
[garrytan/gstack `diagram/SKILL.md`](https://github.com/garrytan/gstack/blob/main/diagram/SKILL.md),
[`SKILL.md.tmpl`](https://github.com/garrytan/gstack/blob/main/diagram/SKILL.md.tmpl),
[`lib/diagram-render/src/entry.ts`](https://github.com/garrytan/gstack/blob/main/lib/diagram-render/src/entry.ts),
[`lib/diagram-render/README.md`](https://github.com/garrytan/gstack/blob/main/lib/diagram-render/README.md),
and [`bin/gstack-render.ts`](https://github.com/garrytan/gstack/blob/main/bin/gstack-render.ts).

The gstack skill is a **workflow around a dedicated renderer**, not just an
LLM prompt. It takes a small Mermaid flow or sequence diagram and delivers
Mermaid source, SVG/PNG and an Excalidraw scene. The local browser loads a
self-contained HTML bundle built from pinned Mermaid and Excalidraw packages.
Source is passed into the page using base64 rather than interpolating user text
into JavaScript. The renderer checks hard parse errors and page errors, and
the skill requires visually reviewing PNG output.

## Capability comparison

| Capability | gstack /diagram | diagram-generator |
| --- | --- | --- |
| Main input | User's natural-language or Mermaid description | AWS, Terraform, JSON, Kubernetes, Helm, authored YAML/JSON specs, trusted Python |
| Canonical machine-readable graph | Mermaid input | Graph JSON, Mermaid, authored spec |
| SVG and PNG | Offline browser bundle | Mermaid CLI or python-diagrams/Graphviz, container-first |
| Editable scene | `.excalidraw` | `.drawio` with native XML cells and connectors |
| Flowchart/sequence editability | Element-editable in Excalidraw | draw.io editable for native graph/spec renders |
| Other Mermaid diagram kinds | Image-only Excalidraw element fallback | Mermaid SVG/PNG; no Excalidraw export |
| Source collection and blind spots | Not an inventory collector | Collectors, source metadata, blind-spot reports |
| Editing round-trip | Excalidraw scene -> SVG/PNG via bundle | draw.io edits do not round-trip into graph/spec |
| Offline rendering requirements | Bun + local prebuilt browser bundle and browser engine | Project container includes mmdc + Graphviz |
| CI and tests | Browser bundle and renderer-specific tests | Container smoke tests, Python pytest tests |

The outputs have different semantics: gstack's `.excalidraw` is **not**
equivalent to a draw.io file, and a diagram-generator Mermaid image is **not**
guaranteed to have the same layout as the Graphviz draw.io export. Generated
draw.io exports contain separate editable cells; they do not reproduce a
hand-drawn Excalidraw style.

## Adopted in this PR

1. **One-command review bundle.** `diagram-gen --review-bundle` adds
   `.diagram.svg`, `.diagram.png`, and editable `.diagram.drawio`, with the
   existing `.graph.json` and `.mmd` source files, packaged in a ZIP. All
   presentation formats use the existing Graphviz backend for consistency.
2. **Direct Mermaid rendering for small narrative diagrams.**
   `diagram-gen mermaid --input diagram.mmd` also accepts a Markdown Mermaid
   fence; it produces normalized `.mmd`, `.svg`, and `.png`. It stages all
   images first and publishes only after successful rendering.
3. **An agent-facing SKILL.md.** `skills/diagram-generator/SKILL.md` formalizes
   source selection, evidence/provenance, output verification, visual review,
   and editable-file delivery without making gstack a runtime dependency.
4. **Regression checks.** Pytest covers new CLI parsing, output selection,
   fenced source extraction, successful rendering orchestration and failure
   without newly published partial artifacts.

## Deliberately not copied

- **gstack's generated boilerplate/preamble, telemetry, model patches, or
  browser runtime.** Those are gstack-specific concerns and are unnecessary
  for diagram-generator. We do not vendor the 7+ MB HTML bundle.
- **Excalidraw labels on draw.io files.** Editors and formats differ.
- **An Excalidraw exporter in this PR.** It should be implemented only when
  native element editability, arrow bindings, labels, font handling, and
  import/re-export are covered by real integration tests. Blindly converting a
  non-flowchart to a single image element would not improve our graph workflow.
- **Unverified visual QA automation.** Image generation can be tested for
  successful execution, but human/agent inspection of layout remains required.

## Recommended next increments

1. Add optional native Excalidraw export behind a dedicated renderer module,
   with real Excalidraw import and round-trip tests; retain `.drawio`.
2. Consider a renderer-level visual fixture test and SVG structure checks in CI
   for missing labels, disconnected edges, and overly large canvases.
3. Add focus/partition settings for dense inventories without silently dropping
   infrastructure elements; report filtered-out counts in a manifest.
4. Add a machine-readable artifact manifest including source provenance,
   output hashes, timestamps, warnings, and expected source/render formats.
5. Keep example and research diagrams small; split topology, identity/data
   flow, deployment, and failure domains when readability demands it.

## Commands

For a collected graph:

```bash
./scripts/build-container.sh
./scripts/run-container.sh --source json \
  --json tests/snapshots/simple_graph.graph.json \
  --out-dir output --name example --review-bundle
./scripts/check-container.sh
```

Expected bundle: `output/example/example.graph.json`,
`output/example/example.mmd`, `output/example/example.diagram.svg`,
`output/example/example.diagram.png`,
`output/example/example.diagram.drawio`, the Graphviz `.dot` intermediate,
and `output/example.zip`.

For a user-authored Mermaid flow:

```bash
./scripts/run-container.sh mermaid --input example.mmd \
  --out-dir output --output flow
```

Expected: `output/flow.mmd`, `output/flow.svg`, `output/flow.png`.
No Excalidraw or draw.io output is implied by this command.

**Security:** Do not share infrastructure graph JSON, ZIP archives or
Mermaid content without reviewing embedded labels, attrs and metadata.
Do not treat successful rendering as proof of live infrastructure accuracy.
