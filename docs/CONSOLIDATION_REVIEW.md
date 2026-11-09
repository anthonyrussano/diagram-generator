# Consolidation review: diagram-generator, gstack, Ferroprint, statechart-generator

Reviewed 2026-11-08. Consolidation target:
[anthonyrussano/diagram-generator](https://github.com/anthonyrussano/diagram-generator).

Sources reviewed:

- [gstack's diagram skill](https://github.com/garrytan/gstack/blob/main/diagram/SKILL.md),
  its template and browser renderer. See
  [GSTACK_DIAGRAM_COMPARISON.md](GSTACK_DIAGRAM_COMPARISON.md).
- [Ferroprint](https://github.com/anthonyrussano/ferroprint), particularly
  `README.md`, `docs/LIVE.md`, `src/engine.js`, `src/mermaid.js`,
  `src/layout.js`, `scripts/export.mjs` and its test suite.
- [statechart-generator](https://github.com/anthonyrussano/statechart-generator),
  including `AGENTS.md`, the vendored skill, TLA+/TLC wrappers, pinned
  bootstrap, example policies, and Pele SVG renderer.

## What each repo brings

| Tool | Strength | Best role in the unified project |
| --- | --- | --- |
| diagram-generator | Read-only infrastructure inventory, authored YAML/JSON, graph normalization, draw.io, SVG/PNG, reportable blind spots | Canonical graph/collector engine and agent entrypoint |
| gstack /diagram | Consistent source + preview + editable output; Excalidraw conversion; offline rendering | Source-first review contract; Excalidraw is a future optional adapter |
| Ferroprint | Browser-based editor for many diagram types, cloud shapes, live on-disk JSON/Mermaid collaboration, PNG/SVG/PDF export | Optional, portable **native Ferroprint project JSON** export for manual refinement |
| statechart-generator | Real TLA+ model checking, invariant/property outcomes, shortest bug paths, nested/parallel statechart rendering | Isolated and vendored TLA+/TLC module exposed by the same CLI |

## Adopted

### Ferroprint interoperability

`diagram-gen --ferroprint` adds `<name>.ferroprint.json` to the ordinary
collector output. `--review-bundle` includes that editable artifact automatically
alongside graph JSON, Mermaid, draw.io, SVG/PNG and ZIP.

The exporter uses the documented Ferroprint project/sheet/node/connector schema.
It keeps a deterministic, grid-aligned simple layout without requiring a
JavaScript browser or duplicating Ferroprint's proprietary/unlicensed engine
implementation. IDs are normalized to Ferroprint-safe shape IDs; relationships,
labels and supported generic shape types are kept. Raw graph attributes are
**not** copied into the editor document, since they can include secrets or
other internal details. The `.graph.json` is still a separate sensitive
machine-readable source.

**Limits:** This is an interoperable document, **not a bundled browser app**.
Open the JSON via Ferroprint's **Open** action, then export PNG/SVG/PDF there.
It may choose different connector routes from Graphviz/draw.io. The layout is
a straightforward deterministic layer assignment, not dagre; cycles share a
fallback layer. Self-loops and absent endpoints are rejected rather than
silently discarded by Ferroprint's importer. Cloud icons are intentionally
not guessed; users may add them in the editor.

### TLA+/TLC statechart consolidation

The MIT-licensed, pinned runtime and smoke example are under
`integrations/statechart/` (including a nested package lock and MIT license).
Python/Graphviz and Java/TLC/Pele dependencies remain separated. The
`diagram-gen statechart` command delegates to the vendored checker and can
render with Pele. Exit 1 signals a rule violation, not an infrastructure
collection failure; the handoff must clearly distinguish modeled bugs from
validated production defects.

Read [integrations/statechart/README.md](../integrations/statechart/README.md)
for setup, examples and limitations. The optional runtime is not installed by
the default image and model checking requires a one-time bootstrap.

### gstack-inspired review contract

The main CLI now supports a consistent review artifact directory/ZIP,
direct Mermaid rendering and an agent-facing skill. The source should
remain editable and previews must be actually rendered and inspected.
For workflow details read [the agent skill](../skills/diagram-generator/SKILL.md).

## Not merged (and why)

- **Ferroprint browser app** (React/JS/editor, IndexedDB, service worker, icons):
  the source repository does not expose a root license file in the reviewed tree
  and links to an upstream author's site. Before copying the application into
  this repository, verify the underlying redistribution and cloud icon licenses,
  and decide whether to maintain a JavaScript web subproject. The JSON adapter
  already permits agent-generated diagrams to be edited in that app today.
- **Ferroprint cloud icon collections:** provider trademarks and license rules
  differ; the current project has its own icon catalog. Avoid unverified assets.
- **gstack's Excalidraw browser bundle:** substantial pinned JS dependencies,
  a dedicated browser daemon and a 7+ MB generated HTML file. It should be a
  separately tested optional renderer if adopted.
- **Statechart vendor test corpus:** the core runtime, examples and license
  migrated; the full many-file fixture corpus remains at its pinned original
  repo to avoid carrying generated TLC outputs and large test data. Changes to
  the vendored TLA engine need upstream suite verification.
- **Arbitrary Python execution for reading project JSON:** no executable
  Ferroprint code runs during native document export. Only the explicit trusted
  Python authoring and optional statechart workflows execute programs.

## One project, three authoring workflows

1. Infrastructure / cloud graph: collector -> graph JSON / Mermaid ->
   native draw.io + Ferroprint JSON + SVG/PNG + ZIP.
2. Conceptual flow / sequence / standard Mermaid: `diagram-gen mermaid`
   -> normalized `.mmd` + rendered SVG/PNG; edit source, rerender.
3. Behavior, failover and policy correctness: `diagram-gen statechart`
   -> TLA+/TLC report + Mermaid statechart + optional Pele SVG/PNG.

The diagram generator is the primary *repository and CLI*. Editing in a browser
remains optional: diagrams.net can open `.drawio` and Ferroprint can open its
JSON format. Browser editing does not round-trip automatically to the canonical
graph or YAML inputs.

## Suggested follow-ups

- Add Ferroprint layout import/export round-trip integration tests against the
  real app as a separate optional job, and a native editor launch workflow if
  licensing and maintainership are settled.
- Add spec/YAML -> Ferroprint project export with clusters as editable zones.
- Add visual regression fixtures and a provenance manifest listing sources,
  confidence, warnings, output hashes and exact renderer versions.
- Run the full upstream TLC corpus if the vendored runtime is modified.
