#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd)
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
    docker)
        exec docker run --rm \
            --user "$(id -u):$(id -g)" \
            --volume "${repo_root}:/workspace" \
            "${image_name}" "$@"
        ;;
    podman)
        exec podman run --rm \
            --userns=keep-id \
            --volume "${repo_root}:/workspace:Z" \
            "${image_name}" "$@"
        ;;
    *)
        echo "Unsupported container engine '${container_engine}'; use docker or podman." >&2
        exit 1
        ;;
esac
