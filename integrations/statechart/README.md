# Integrated model-checked statecharts

This optional module was consolidated from
[anthonyrussano/statechart-generator](https://github.com/anthonyrussano/statechart-generator)
as a self-contained addition to `diagram-generator`. Its engine is the pinned
[Cursor statechart skill](https://github.com/cursor/plugins/tree/main/pstack/skills/statechart),
MIT licensed, with provenance recorded in
[`vendor/statechart/UPSTREAM`](vendor/statechart/UPSTREAM) and
[`vendor/statechart/LICENSE`](vendor/statechart/LICENSE).

**Purpose:** Explore TLA+ state machines with TLC and produce Mermaid statecharts
and reports that mark shortest paths to broken rules. This is **model checking**,
not merely rendering a `stateDiagram-v2` string.

## One-time optional setup

```bash
cd integrations/statechart
./scripts/bootstrap.sh
./scripts/check.sh
cd ../..
```

Requires Node 22.18+ or 23.6+, npm, curl, sha256sum and Bash. The bootstrap
downloads checksum-verified TLC and Java into this integration's `.tools`
directory and installs Pele inside this integration's `node_modules`. On
non-Linux-x64 hosts, set `JAVA` to an installed Java 11+ binary; the bootstrap
only provides a Linux x64 JRE automatically.

The runtime is **not** installed into the standard diagram generator container
by default. This prevents Java/TLC/Pele requirements from affecting AWS,
Terraform, Kubernetes, Mermaid, draw.io, or Ferroprint workflows.

## Invoke through the shared CLI

```bash
uv run diagram-gen statechart \
  --spec integrations/statechart/examples/group-provisioning/GroupProvisioning.tla \
  --config integrations/statechart/examples/group-provisioning/none.cfg \
  --view integrations/statechart/examples/group-provisioning/view.mjs \
  --out output/statechart-none --render svg
```

For PNG use `--render png`, which uses the integration's Pele theme and
Chromium via Docker/Podman. The wrapper runs as the calling user and writes
outputs to a new or empty folder.

- Exit **0**: all checked invariants/properties hold.
- Exit **1**: TLC found a broken rule; this is an important modeled finding,
  **not** evidence that the tool itself crashed. The report and chart are
  generated when possible.
- Exit **2**: model-checking or rendering failed (other runtime error codes
  may be returned from the upstream wrapper).

Expected outputs include `report.md`, `chart.mmd`, `tlc.out`, and optional
SVG/PNG. When the 500-state chart budget is exceeded, a model with no broken
rules may generate no chart. The report still contains the verification result.

Do not weaken an invariant to obtain a clean report. State the model's
assumptions and omissions; call an identified bug path **model only** until
replayed against the real system.

The upstream project's test corpus was not copied here. The vendored runtime
is pinned to the source commit, and the source repository's full regression
suite remains authoritative for changes to the vendor code. Run
`./scripts/check.sh` after bootstrapping and before upgrading the vendor.
