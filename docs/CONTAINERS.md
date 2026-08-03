# Container setup: Podman, Docker, and GHCR

The project ships one OCI-compatible CLI image. It does not require Compose and does not run sibling containers.

The image includes:

- `diagram-gen` with the `dev`, `render`, and `aws-boto3` extras
- AWS CLI v2
- `kubectl`
- Helm
- Graphviz (`dot`)
- Mermaid CLI (`mmdc`), Chromium, and fonts
- `uv` and pytest

Mermaid uses native `mmdc` inside the image. This is intentional: no Docker or Podman socket needs to be mounted into the container.

## Build locally

Podman (recommended on this host):

```bash
podman build --file Containerfile --tag diagram-gen:local .
```

Docker:

```bash
docker build --file Containerfile --tag diagram-gen:local .
```

The build pins default tool versions with `ARG` values in `Containerfile`. Override a version when testing an upgrade:

```bash
podman build \
  --build-arg KUBECTL_VERSION=v1.36.3 \
  --build-arg HELM_VERSION=v4.2.3 \
  --tag diagram-gen:local \
  --file Containerfile .
```

Base-image tags are also pinned to immutable manifest digests, and Mermaid's transitive npm dependencies are locked in `containers/package-lock.json`. When changing a base-image version, update its digest at the same time.

The full toolchain is intentionally substantial: the local image is about 2 GB uncompressed because it includes Chromium, AWS CLI, Graphviz, both rendering stacks, and the test environment. Registry transfer and storage use compressed layers.

## Run with Podman

Show help:

```bash
podman run --rm diagram-gen:local --help
```

Generate all local output formats from a checked-out repository:

```bash
podman run --rm \
  --userns=keep-id \
  --volume "$PWD:/workspace:Z" \
  diagram-gen:local \
  --source json \
  --json tests/snapshots/simple_graph.graph.json \
  --out-dir output \
  --name container-smoke \
  --svg --png \
  --diagram-format svg \
  --diagram-format png
```

`:Z` gives a private SELinux label to the bind mount. On systems without SELinux labeling, omit the suffix if the engine rejects it.

## Run with Docker

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" \
  diagram-gen:local \
  --source json \
  --json tests/snapshots/simple_graph.graph.json \
  --out-dir output \
  --name container-smoke \
  --svg --png \
  --diagram-format svg \
  --diagram-format png
```

Docker Desktop users can usually omit `--user` if host UID/GID mapping is not available.

## Live AWS and Kubernetes access

Credentials and cluster configuration are not baked into the image. Mount only the configuration needed for a run, preferably read-only.

AWS example with Podman:

```bash
podman run --rm \
  --userns=keep-id \
  --volume "$PWD:/workspace:Z" \
  --volume "/path/to/.aws:/home/diagram/.aws:ro,Z" \
  diagram-gen:local \
  --source aws \
  --profile default \
  --region us-east-1 \
  --out-dir output \
  --name aws-live
```

Kubernetes example with Podman:

```bash
podman run --rm \
  --userns=keep-id \
  --volume "$PWD:/workspace:Z" \
  --volume "/path/to/.kube:/home/diagram/.kube:ro,Z" \
  diagram-gen:local \
  k8s summarize --namespaces default
```

Use the equivalent Docker bind mounts without `:Z`. The container must be able to reach the AWS and Kubernetes API endpoints referenced by those configurations.

## Host-side Mermaid rendering

The non-containerized CLI can select Docker or Podman automatically:

```bash
uv run diagram-gen \
  --source json \
  --json tests/snapshots/simple_graph.graph.json \
  --out-dir output \
  --name podman-mermaid \
  --svg --png \
  --mermaid-runtime container \
  --container-engine podman
```

Selection rules:

1. `--mermaid-runtime auto` uses native `mmdc` when available.
2. Otherwise it selects Docker first, then Podman.
3. Use `--container-engine podman` or `docker` to make the choice explicit.

Container-based rendering defaults to the official, versioned Mermaid CLI image at
`ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0`. Override it with
`--mermaid-image` when testing an upgrade or an internal mirror.

## Pull from GitHub Container Registry

After the publishing workflow completes:

```bash
podman pull ghcr.io/anthonyrussano/diagram-generator:latest
podman run --rm ghcr.io/anthonyrussano/diagram-generator:latest --help
```

Docker uses the same image name:

```bash
docker pull ghcr.io/anthonyrussano/diagram-generator:latest
```

The workflow publishes OCI images on pushes to `main`, version tags matching `v*`, and manual dispatches. Pull requests build and smoke-test the image without publishing it. Published tags include `latest` for the default branch, the branch or version tag, and a commit-SHA tag.

GitHub Actions authenticates with the repository-scoped `GITHUB_TOKEN`; no PAT secret is required. The workflow grants `packages: write` only to the publish job and adds a provenance attestation. GitHub Container Registry initially creates a package as private unless repository/account settings say otherwise. Change visibility in the package settings if anonymous pulls are desired.

For a manual push, authenticate either engine with a classic PAT scoped to `write:packages`:

```bash
printf '%s' "$CR_PAT" | podman login ghcr.io --username YOUR_GITHUB_USER --password-stdin
podman tag diagram-gen:local ghcr.io/YOUR_GITHUB_USER/diagram-generator:dev
podman push ghcr.io/YOUR_GITHUB_USER/diagram-generator:dev
```

Relevant upstream documentation:

- [Podman CLI](https://docs.podman.io/en/latest/markdown/podman.1.html)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Publishing container images with GitHub Actions](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)

## Compose is optional

This repository does not need or ship a Compose file because it runs a single CLI container.

`podman compose` is a thin wrapper around an external provider. If a future multi-container workflow needs Compose, install either `podman-compose` or `docker-compose`, then verify:

```bash
podman compose version
```

The provider can be selected with `PODMAN_COMPOSE_PROVIDER` or `compose_providers` in `containers.conf`. See the [Podman Compose documentation](https://docs.podman.io/en/latest/markdown/podman-compose.1.html).

## Verify the image toolchain

```bash
podman run --rm --entrypoint sh diagram-gen:local -c '
  diagram-gen --help >/dev/null &&
  aws --version &&
  kubectl version --client=true &&
  helm version --short &&
  dot -V &&
  mmdc --version
'
```

Run the test suite inside the image:

```bash
podman run --rm --entrypoint sh diagram-gen:local -c 'cd /app && pytest tests/ -q'
```
