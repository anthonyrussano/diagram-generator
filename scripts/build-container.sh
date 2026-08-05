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

if ! command -v "${container_engine}" >/dev/null 2>&1; then
    echo "Container engine '${container_engine}' is not available." >&2
    exit 1
fi

chop_ca=${DIAGRAM_GEN_CHOP_CA:-${repo_root}/../helm-charts/network-diagnostics/image/choprootca.crt}
netskope_ca=${DIAGRAM_GEN_NETSKOPE_CA:-${repo_root}/../helm-charts/network-diagnostics/image/netskope-root-ca.crt}
build_args=(build --file "${repo_root}/Containerfile" --tag "${image_name}")

if [[ -f "${chop_ca}" ]]; then
    echo "Injecting CHOP root CA: ${chop_ca}"
    sha256sum "${chop_ca}"
    build_args+=(--secret "id=chop_root_ca,src=${chop_ca}")
else
    echo "CHOP root CA not found at ${chop_ca}; using the standard trust store."
fi

if [[ -f "${netskope_ca}" ]]; then
    echo "Injecting Netskope root CA: ${netskope_ca}"
    sha256sum "${netskope_ca}"
    build_args+=(--secret "id=netskope_root_ca,src=${netskope_ca}")
else
    echo "Netskope root CA not found at ${netskope_ca}; using the standard trust store."
fi

exec "${container_engine}" "${build_args[@]}" "${repo_root}"
