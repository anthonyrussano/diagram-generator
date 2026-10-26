# HCL, manifest relationships, Python authoring, and draw.io export

Run these commands from the repository root, after `./scripts/build-container.sh`.

## Terraform HCL

```bash
./scripts/run-container.sh --source terraform \
  --terraform examples/terraform-hcl \
  --name terraform-example --diagram-format svg --diagram-format drawio
```

The existing Terraform source accepts `.tf` HCL, `.tf.json`, and `.tfstate`.
`--discover` also finds `.tf` files. A directory passed to `--terraform` loads its
immediate `.tf` and `.tf.json` files together as one module. Pass multiple paths
for multiple modules; discovery walks recursively. References resolve across files
in the same directory. Independent directories are qualified in node IDs to keep
identically named resources separate. State resources retain their `module.*`
addresses. A root resource keeps the existing `tf:type.name` ID when collecting
a single directory.

The collector uses `python-hcl2` (included in the base dependencies). It collects
resources, data sources, and module calls, with explicit `depends_on` and implicit
`references` edges. Expressions can include functions, interpolations, and indexed
resources. Plain strings resembling resource addresses are not references. Module
output references connect to the declared module call. State instance dependencies
are also collected.

This is static analysis: it does not run Terraform, load providers, contact APIs,
evaluate locals/variables, expand `count`/`for_each`, or download/expand module calls.
Nodes represent declarations, not planned instances. Invalid files, unresolved
references, and static-analysis limitations appear in graph metadata and
`.blindspots.json/.md`. Other valid files continue to contribute resources.

## Kubernetes manifest relationships

```bash
./scripts/run-container.sh --source kubernetes \
  --k8s examples/k8s-relationships.yaml \
  --name manifest-example --diagram-format png --diagram-format drawio
```

Manifest files, Helm-rendered documents, and the existing live collector share
relationship detection. YAML `List` documents are expanded. Supported links:

| Relationship | Meaning |
| --- | --- |
| `owned_by` | Observed `ownerReferences` |
| `selects` | Service selectors matching Pods; otherwise matching workload pod templates |
| `manages` | Workload selectors matching observed Pods, including `matchExpressions` |
| `mounts`, `reads` | ConfigMap/Secret volumes, projections, `env`, and `envFrom` |
| `uses`, `pulls_with` | PVCs, service accounts, and image-pull secrets |
| `routes_to`, `uses_tls` | Ingress backends and TLS secrets |
| `scales` | HPA target |
| `bound_to`, `provisioned_by` | PVC-to-PV and PVC-to-StorageClass |
| `binds_role`, `binds_subject` | RBAC role references and ServiceAccount subjects |

Pod-spec detection includes Deployments, StatefulSets, DaemonSets, ReplicaSets,
Jobs, CronJobs, and Pods, including init and ephemeral containers. Service matching
uses pod-template labels rather than workload metadata labels. Template-derived
links are marked in edge attributes. Namespaced references stay within their
namespace unless explicitly named (for example, RBAC subjects). Known
cluster-scoped kinds use `_cluster` in their IDs.

Only collected resources become nodes or edge endpoints. Missing named references
are warnings; generated StatefulSet PVC names are not guessed. Selectors with no
matches create no links. An edge represents a declared relationship, not proof of
working connectivity. Custom-resource scope/relationships are not inferred from CRDs.

The existing `--live-k8s` query remains `kubectl get all`, which omits some kinds.
Supply additional manifests for config, secrets, storage, or RBAC when absent.
These changes require no new live access or permissions.

## Editable draw.io files

For collected graphs, add `--diagram-format drawio`. For specs, batches, comparisons,
live namespace specs, and `aws-boto3`, select `--format drawio`:

```bash
./scripts/run-container.sh spec --spec examples/spec-architecture.yaml \
  --output architecture --format png --format drawio

./scripts/run-container.sh spec-batch --spec-dir specs \
  --out-dir output/specs --format svg --format drawio
```

Open the `.drawio` file in diagrams.net or draw.io Desktop. Nodes, labels, nested
groups, and attached connectors are separate editable cells. Icons are embedded,
so files do not depend on container paths or external image hosting. Graphviz
positions nodes/groups; editable waypoints approximate its connector bends. Arrow directions, common colors,
line widths, dashed lines, and basic shapes are preserved. Exact Graphviz splines,
HTML labels, custom shapes, and advanced styling are not reproduced. Invisible
layout edges are omitted.

The exporter uses Graphviz JSON layout and Python's XML library. It requires the
existing render dependencies and `dot`, with no `pygraphviz`, development headers,
or extra conversion package. A `.dot` intermediate is retained alongside `.drawio`.
Graph collection bundles include both files and any blind-spot reports.

Manual draw.io edits do not update graph/spec inputs. Keep the source of truth and
edited artifacts clearly named; regeneration overwrites its selected output.

## Python authoring

```bash
./scripts/run-container.sh python --script examples/python-architecture.py \
  --output python-example --format png --format svg --format drawio --timeout 90
```

Use normal Python imports and `with Diagram(...)` contexts. Helpers, loops,
conditionals, and custom Diagrams nodes work normally. Local helper modules and
relative assets resolve from the script's directory. The CLI controls the output
prefix, requested formats, and `show=False`, overriding the script's constructor
values. Multiple diagrams get `-2`, `-3`, etc. Supported formats: `png`, `svg`, `pdf`,
`dot`, `drawio`.

Each script executes once in a separate process. A timeout terminates its process
group, including child renderers. Counts come from the actual authored graph. No
diagrams or a script error fails the command. Partial files can remain on failure.

Python scripts are executable programs: use trusted scripts. The subprocess and
timeout isolate interpreter state and control runtime; they are not a security
sandbox. Container execution has the container user's permissions and access to
the mounted repository; host execution has your user's permissions. Repeatability
depends on the script's I/O, randomness, and time-dependent logic. Save and review
the `.py` source with its artifacts. Python mode does not export the canonical
graph model or infer infrastructure from code.

For host use, install `uv sync --extra render` and Graphviz; replace the wrapper
with `uv run diagram-gen`.

## Implementation references

- [python-hcl2 API](https://github.com/amplify-education/python-hcl2)
- [Graphviz JSON output](https://graphviz.org/docs/outputs/json/)
