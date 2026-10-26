# Feature opportunities from related diagram projects

Reviewed on 2026-10-26 against the local checkouts below. This is a source review
and implementation proposal, not a claim that these features have been added to
`diagram-generator`. The three upstream applications were not installed or run.

| Repository | Reviewed commit | Declared license |
| --- | --- | --- |
| `ansible-playbook-grapher` | `3bf87a820b939c74301213fb4667fbbf043c2d0e` | GPL-3.0-or-later |
| `ansible-inventory-grapher` | `d25fb727b20a6a5222d924be4e1e9c378e64d1c1` | GPLv3; source headers specify version 3 or later |
| `terravision` | `849bf43b8bbe074c0f798777e4eb1e7cc825dda2` | AGPL-3.0-only |

The proposals below use these projects as design references. Any source-code or
asset reuse needs a deliberate licensing and attribution decision. No upstream
code has been copied as part of this review.

## Recommended additions

| Priority | Addition | Benefit and suggested approach |
| --- | --- | --- |
| High | Saved presentation overlays and focused views | Keep collected facts intact while maintaining labels, grouping, evidence status, selected roots, and detail levels across regeneration. Useful for all sources and session-based diagrams. |
| High | Terraform plan JSON import | Complement static HCL with evaluated module/resource instances, resolved values, and planned actions from an existing plan export. Start with file input rather than running Terraform. |
| High when using Ansible | Inventory import | Show group/child-group/host membership and a selected host or group's context. Start with exported inventory JSON, with variable values excluded by default. |
| High | Source locations and evidence links | Record file/line or collection-command provenance on nodes and relationships; expose optional source links and evidence notes in outputs. |
| Medium | Ansible playbook import | Show playbook → plays → roles/blocks/tasks, conditions, declared order, and handler notifications. Start with an adapter for the playbook grapher's versioned JSON output. |
| Medium | Standalone interactive HTML | Add search, zoom, relationship highlighting, metadata details, and collapsible groups without requiring a running service. |
| Medium | Provider-aware presentation rules | Map common Terraform types to icons and group observed resources by region/VPC/subnet or equivalent cloud boundaries. Separate containment from dependencies and traffic. |
| Lower | Native draw.io cloud shapes | Supplement current editable image nodes with native provider shapes where mappings are known, retaining embedded-image fallback. |

## ansible-inventory-grapher

The useful distinction is between **inventory structure** and network topology.
This project discovers hosts matching Ansible patterns, walks their parent groups,
and renders group/host relationships. Its variable handling removes inherited or
overridden duplicates so each host's effective context is easier to understand.
Variable names and selected values can be displayed independently.

Source evidence:

- [`parent_graphs`, variable handling, and `generate_graph_for_host`](https://github.com/willthames/ansible-inventory-grapher/blob/d25fb727b20a6a5222d924be4e1e9c378e64d1c1/ansibleinventorygrapher/__init__.py)
- [Inventory and variable managers](https://github.com/willthames/ansible-inventory-grapher/blob/d25fb727b20a6a5222d924be4e1e9c378e64d1c1/ansibleinventorygrapher/inventory.py)
- [Host-pattern selection and variable visibility controls](https://github.com/willthames/ansible-inventory-grapher/blob/d25fb727b20a6a5222d924be4e1e9c378e64d1c1/ansibleinventorygrapher/__main__.py)

Suggested integration:

- Add a distinct inventory collector with group/host kinds and explicitly named
  membership relationships. Preserve multiple memberships: inventory is a graph,
  not necessarily a single-parent tree.
- Initially accept previously exported `ansible-inventory --list` JSON. A later,
  explicit collection mode can run Ansible when users need dynamic inventory.
- Offer host/group focus and optional variable-name or allowlisted-value views.
  A resolved inventory export alone does not establish which file/group supplied
  each variable; variable-origin tracing needs separate provenance collection.
- Keep variable values out of default artifacts, including canonical graph JSON.
  An inventory loader can use dynamic plugins; importing an export avoids invoking
  those during ordinary diagram rendering.

Do not copy the internal Ansible manager implementation wholesale. It depends on
Ansible internals, while an exported-data adapter can remain a small independent
collector. Membership edges must never be relabeled as working network links.

## ansible-playbook-grapher

This project adds a different source: **automation structure**. Its parser models
plays, pre/post tasks, roles, blocks, tasks, includes/imports, conditions, and
handlers. It offers role-only or expanded views, tag filtering, role grouping,
source locations, and interactive SVG behavior.

Source evidence:

- [Parser, task conditions, filters, and includes](https://github.com/haidaraM/ansible-playbook-grapher/blob/3bf87a820b939c74301213fb4667fbbf043c2d0e/ansibleplaybookgrapher/parser.py)
- [Node locations, order indices, and notification relationships](https://github.com/haidaraM/ansible-playbook-grapher/blob/3bf87a820b939c74301213fb4667fbbf043c2d0e/ansibleplaybookgrapher/graph_model.py)
- [Versioned JSON renderer](https://github.com/haidaraM/ansible-playbook-grapher/blob/3bf87a820b939c74301213fb4667fbbf043c2d0e/ansibleplaybookgrapher/renderer/json.py)
- [Interactive SVG postprocessing](https://github.com/haidaraM/ansible-playbook-grapher/blob/3bf87a820b939c74301213fb4667fbbf043c2d0e/ansibleplaybookgrapher/renderer/graphviz/postprocessor.py)

Suggested integration:

- Import the versioned JSON into `GraphData`, preserving composition, declared
  order, `when`, `notify`/`listen`, and source location. Validate supported schema
  versions and report unresolved references.
- Derive stable IDs from source identity and parent context. Upstream's default
  `generate_id()` uses random UUIDs, which should not become persistent canonical
  IDs for comparisons or presentation overlays.
- Offer summary and task-level views while preserving the complete imported model.
  Maintain separate containment, declared-order, and notification relationships.
- Generalize source-location links and focused views for other collectors too.

The graph describes static playbook structure, not a record of successful task
execution. Upstream documents unresolved dynamic includes/variables and represents
loops as one task. Its dependency on `ansible-core>=2.16,<2.18.3` is a reason to
isolate an optional external parser rather than add it to the base environment.
Interactive SVG support also depends on the viewer; its injected jQuery URL is
external. A separate self-contained HTML output would suit portable exploration.

## TerraVision

The largest accuracy improvement to borrow is **plan-derived input**, complementing
our declaration-based HCL collector. TerraVision combines plan data, Terraform's
dependency graph, source metadata, provider-specific enrichment, and annotation
files. It also implements numbered flow legends, logical grouping, an interactive
HTML output, and native draw.io provider shapes.

Source evidence:

- [Input selection and enrichment pipeline](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/terravision/terravision.py)
- [Pre-generated plan/graph inputs and Terraform execution](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/modules/tfwrapper.py)
- [Module output resolution using plan expressions and values](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/modules/plan_resolver.py)
- [Annotations, groups, connection labels, and numbered flows](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/docs/annotations.md)
- [Self-contained HTML assembly](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/modules/html_renderer.py)
- [Native provider draw.io shapes and image fallback](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/modules/drawio_emitter.py)
- [Layout regression test for legend/footer clearance](https://github.com/patrickchugh/terravision/blob/849bf43b8bbe074c0f798777e4eb1e7cc825dda2/tests/test_legend_clearance.py)

Suggested integration:

1. **Accept an existing plan JSON export.** Preserve exact indexed addresses,
   module nesting, known/unknown and sensitive markers, and create/update/delete
   actions. Exclude or redact marked sensitive values before writing shareable
   artifacts, including graph JSON. Include unchanged planned resources, not just changed ones. Resolve
   relationships from available configuration references and optionally supplied
   Terraform graph data; report gaps. TerraVision's pre-generated mode currently
   requires plan JSON plus a DOT graph and source input, so a file-first importer
   for our project is an independent design rather than a drop-in wrapper.
2. **Add versioned presentation overlays.** Keep labels, layout groups, numbered
   flow steps, and evidence status separate from collected facts. Authored additions
   must carry explicit provenance. Reject unknown IDs and report omitted resources.
   Existing YAML specs already support manual styling/grouping; the new benefit is
   applying saved presentation choices to regenerated collector output.
3. **Add provider presentation profiles.** Use observed region/VPC/subnet references
   for containment and a tested type-to-icon catalog. Preserve the canonical graph
   while supporting summary views. Avoid turning security policy references into
   claims of established connectivity.
4. **Add an optional HTML renderer.** Embed SVG, required scripts, and selected
   metadata locally, with search and focused exploration. Allowlist metadata for
   shareable output rather than embedding every raw source attribute.
5. **Expand output verification.** Add layout checks for legend/label clearance and
   source-to-output identity mapping when introducing those features. Retain visual
   inspection; geometry tests cannot establish semantic correctness.

TerraVision also uses implied connections, synthetic parent nodes, consolidation,
and synthetic instance counts (`graphmaker.py`). Those transformations should not
become unmarked infrastructure facts in our evidence-oriented model. Display-only
copies or containers need explicit provenance and a path back to the observed node.

Its default Terraform path runs init/plan and uses temporary backend/provider
handling. Keep such execution separate from ordinary file rendering. An existing
plan describes intended state and may contain unknown values; it does not establish
live deployment or working connectivity. TerraVision also pins `python-hcl2==4.3.0`,
which conflicts with our `>=7.3.1,<8` requirement in a shared environment.

## Suggested implementation order

1. Define source/evidence metadata and a presentation/view layer shared by inputs.
2. Add saved Terraform plan and inventory JSON collectors with synthetic fixtures.
3. Add the playbook JSON adapter and summary/detail views.
4. Add saved overlays, numbered flows, and the optional offline HTML renderer on
   the common view model; improve provider grouping and icon mappings as needed.
5. Add native draw.io stencils when their editing benefits justify the mapping work.

Acceptance should include stable IDs, deterministic regeneration, multiple group
membership, unresolved-reference reporting, sensitive-value handling, and preservation
of the full canonical graph when a presentation hides or aggregates nodes. None
of these features requires adding MCP or another model/API dependency.
