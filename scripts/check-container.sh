#!/usr/bin/env bash
set -euo pipefail

image_name=${DIAGRAM_GEN_IMAGE:-diagram-gen:local}
container_engine=${CONTAINER_ENGINE:-}

if [[ -z "${container_engine}" ]]; then
    if command -v docker >/dev/null 2>&1; then
        container_engine=docker
    elif command -v podman >/dev/null 2>&1; then
        container_engine=podman
    else
        echo "Neither Docker nor Podman is available." >&2
        exit 1
    fi
fi

case "${container_engine}" in
    docker|podman) ;;
    *)
        echo "Unsupported container engine '${container_engine}'; use docker or podman." >&2
        exit 1
        ;;
esac

"${container_engine}" run --rm --workdir /app --entrypoint uv \
    "${image_name}" run pytest tests/ -v

"${container_engine}" run --rm --workdir /app --entrypoint /bin/bash \
    "${image_name}" -lc \
    'uv run python -m py_compile src/agent_diagrams/*.py src/agent_diagrams/renderers/*.py'

"${container_engine}" run --rm "${image_name}" --help >/dev/null
echo "Container tests, compilation, and CLI help checks passed."
