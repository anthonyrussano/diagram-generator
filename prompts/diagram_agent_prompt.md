# Session-based diagram prompt

Use this prompt when introducing `diagram-generator` during an investigation or
build session. Fill in the brief where useful; the agent can infer routine details
from the current session and report its assumptions.

## Copyable request

> Use `~/Projects/diagram-generator` to diagram **[the system or flow]** based on
> our latest findings and decisions in this session.
>
> Read its `AGENTS.md`, `AGENT_WORKFLOW.md`, and relevant authoring documentation
> first. Use this repository as the generator; keep the task scoped to diagram
> inputs, notes, and artifacts unless I request generator changes.
>
> The diagram should explain **[one main question]** for **[the intended audience]**.
> Represent **[current state / proposed design / current versus proposed]**.
> Distinguish confirmed facts, inferences, and planned components, and flag anything
> unresolved. Use the latest conclusions rather than superseded hypotheses.
>
> Prefer a YAML spec unless another supported workflow is more suitable. Save the
> source and brief evidence/assumption notes alongside PNG, SVG, and draw.io outputs
> under **[destination]**.
>
> Follow the container workflow. Label relationships clearly, inspect the rendered
> PNG, and fix readability issues before finishing. Report the files produced,
> node/edge counts, validation performed, and meaningful limitations.

## Agent execution guidance

1. **Establish the brief.** Identify the question, audience, scope, state, and
   destination from the request and session. Split distinct questions into focused
   diagrams when useful. Resolve routine choices autonomously; clarify only material
   ambiguity that the available context cannot resolve.
2. **Reconcile the evidence.** Distinguish observed runtime facts, configuration
   declarations, inferred relationships, and agreed design decisions. A resource
   declared in HCL or YAML is not proof it exists or works at runtime. Do not add
   infrastructure or connections merely because they are common in similar designs.
   Label proposed components as proposals and retain unresolved findings in notes.
3. **Choose the authoring path.** Use YAML/JSON specs for session-based synthesis,
   collectors for infrastructure extraction, `compare` for current/future views,
   and trusted Python when helpers, loops, or custom composition materially simplify
   authoring. See `docs/SPECS.md` and `docs/AUTHORING_AND_EXPORT.md`.
4. **Keep relationship semantics explicit.** Ownership, configuration references,
   dependencies, network connections, and data flows are distinct. Label arrows
   accordingly. Add a legend when colors or line styles encode uncertainty,
   planned state, or different relationship types.
5. **Save reproducible inputs.** Keep stable IDs and the spec, graph input, or Python
   script with the artifacts. Record scope, observation date when relevant, evidence
   paths/commands, assumptions, and unresolved gaps in a short accompanying note.
   Link to evidence rather than copying the conversation or credential-bearing output.
   Keep durable inputs outside disposable build folders and separate discovery roots
   from generated outputs.
6. **Render through the container.** Follow the repository build, run, and validation
   wrappers. Validate authored specs before rendering. Use paths available inside
   the container; copy final inputs and artifacts to the requested destination
   afterward if it is outside the wrapper's mounted workspace. Avoid unrelated
   directory scans and unnecessary live infrastructure queries.
7. **Inspect the actual result.** Confirm counts and output files, then open the PNG
   and check clipping, overlap, grouping, arrow direction, and routing. Revise and
   rerender until readable. Compilation or Graphviz success alone is not visual
   verification; report if image inspection is unavailable.
8. **Deliver maintainable artifacts.** Provide the source, evidence/assumption note,
   PNG, SVG, and draw.io files unless the user requested different formats. Read
   blind-spot reports and explain relevant gaps. Review labels and shareable bundles
   for private values; collector graph JSON can contain raw source attributes.

## Choosing a command

Run from the generator repository. Replace example paths with the selected inputs;
do not query live infrastructure merely to complete a template.

```bash
./scripts/build-container.sh

# Session-based architecture: validate, then render a saved YAML spec.
./scripts/run-container.sh spec --spec diagrams/topic/architecture.yaml --check
./scripts/run-container.sh spec --spec diagrams/topic/architecture.yaml \
  --output diagrams/topic/architecture --format png --format svg --format drawio

# Extract declarations and references from Terraform HCL.
./scripts/run-container.sh --source terraform --terraform path/to/module \
  --out-dir output/topic --name architecture \
  --diagram-format png --diagram-format svg --diagram-format drawio

# Extract manifest relationships, including Helm-rendered resources.
./scripts/run-container.sh --source kubernetes --k8s path/to/manifests.yaml \
  --out-dir output/topic --name architecture \
  --diagram-format png --diagram-format svg --diagram-format drawio
./scripts/run-container.sh --source kubernetes --helm-chart path/to/chart \
  --helm-values path/to/values.yaml --out-dir output/topic --name architecture \
  --diagram-format png --diagram-format svg --diagram-format drawio

# Use the full Diagrams DSL when a script is more appropriate.
./scripts/run-container.sh python --script diagrams/topic/architecture.py \
  --output diagrams/topic/architecture --format png --format svg --format drawio
```

Choose one authoring path; these examples are alternatives. Follow `AGENTS.md`
for the required verification commands.

Manual draw.io edits do not update YAML, JSON, or Python inputs. Keep manually
edited versions clearly named and regenerate future revisions from the chosen
source of truth. Python authoring executes trusted code with the runtime user's
permissions; the subprocess timeout is not a security sandbox.
