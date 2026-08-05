# Node icon catalog

Branded and technology-specific icons are available in non-Mermaid renders:

- graph mode: `--diagram-format svg|png|pdf`
- spec mode: `diagram-gen spec --format svg|png|pdf`
- compare and live Kubernetes modes, which also use `python-diagrams`

Plain Mermaid source and Mermaid-rendered `--svg` / `--png` outputs continue to
use Mermaid shapes. They do not load the Graphviz icon catalog.

## Coverage

The renderer exposes every public icon shipped by the locked `diagrams`
dependency—more than 2,600 icons—as a stable canonical name:

```text
provider.category.IconClass
```

Providers include AWS, Azure, Google Cloud, Alibaba Cloud, IBM, Oracle Cloud,
DigitalOcean, OpenStack, Kubernetes, Elastic, Firebase, on-premises DevOps
tools, programming languages/frameworks, and SaaS products. The project also
bundles Supabase and provider-neutral network-interface icons where the
upstream `diagrams` package does not provide an appropriate generic glyph.

Examples:

```text
aws.compute.EC2
azure.compute.VirtualMachine
gcp.compute.ComputeEngine
saas.cdn.Cloudflare
programming.language.Python
programming.framework.React
onprem.container.Docker
onprem.gitops.ArgoCD
custom.supabase.Supabase
custom.local.NetworkInterface
```

List or search the installed catalog:

```bash
uv run --extra render diagram-gen icons --search cloudflare
uv run --extra render diagram-gen icons --provider programming
uv run --extra render diagram-gen icons --search supabase --json
```

## Resolution behavior

Graph nodes are resolved deterministically in this order:

1. An explicit `attrs.icon` value.
2. A recognized filename extension such as `.py`, `.tsx`, `.go`, or `.rs`.
3. The node `kind`.
4. Exact service/tool words in the label and node ID.
5. A blank icon when no accurate match exists.

Unknown kinds are not silently replaced with an unrelated rack or cloud icon.
When graph mode produces a non-Mermaid render, unresolved nodes are printed as
`Icon fallbacks` so the missing coverage can be reviewed.

Common aliases include natural names such as `cloudflare`, `supabase`,
`github-actions`, `python`, `typescript`, `docker`, `postgres`, `terraform`,
`prometheus`, and `grafana`. Canonical names should be used when a short name
could be ambiguous.

## Selecting icons in graph JSON

Use `attrs.icon` to override inference for a node:

```json
{
  "nodes": [
    {
      "id": "backend",
      "label": "Application backend",
      "kind": "service",
      "attrs": {"icon": "supabase"}
    },
    {
      "id": "edge",
      "label": "Edge and DNS",
      "kind": "service",
      "attrs": {"icon": "saas.cdn.Cloudflare"}
    }
  ],
  "edges": []
}
```

Terraform kinds such as `tf.cloudflare_record` and `tf.supabase_project` are
also inferred from their service name.

## Selecting icons in architecture specs

Set the node's `icon` field to an alias, canonical name, or complete
`diagrams.*` class path:

```yaml
nodes:
  - id: api
    label: Python API
    icon: programming.framework.FastAPI
  - id: data
    label: Supabase
    icon: supabase
  - id: edge
    label: Cloudflare
    icon: cloudflare
```

A complete runnable example is available at `examples/icon-catalog.yaml`:

```bash
uv run --extra render diagram-gen spec \
  --spec examples/icon-catalog.yaml \
  --out-dir output \
  --output icon-catalog \
  --format svg
```

## Bundled assets

The Supabase SVG is derived from Simple Icons 16.21.0. A PNG rasterization is
used for Graphviz compatibility; both are stored locally so rendering remains
offline and reproducible. See
`src/agent_diagrams/assets/icons/NOTICE.md` for its source, license, and
trademark notice.

The project-authored `custom.local.NetworkInterface` asset provides a neutral
NIC glyph for local-machine inventory without implying AWS, Azure, GCP, or
another infrastructure provider. Exact `local.network_interface.*` graph kinds
select it automatically.
