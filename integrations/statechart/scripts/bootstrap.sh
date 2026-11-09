#!/usr/bin/env bash
# Install the pinned runtime into .tools/ (Java + TLC) and node_modules/ (Pele).
# Idempotent: skips anything already present and verified.
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tools="${repo_root}/.tools"

TLA2TOOLS_URL="https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar"
TLA2TOOLS_SHA256="936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"
JRE_URL="https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jre_x64_linux_hotspot_25.0.5_8.tar.gz"
JRE_SHA256="6fac98f0c8202efc3135a9e9e42aa61963ec42d1c5cbb40caf231e7b14a24ef6"

if [[ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]]; then
    echo "bootstrap pins a Linux x64 JRE. On other platforms set JAVA to a Java 11+ binary." >&2
fi

command -v node >/dev/null || { echo "node is required (22.18+ or 23.6+)." >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required." >&2; exit 1; }

mkdir -p "${tools}"

if ! echo "${TLA2TOOLS_SHA256}  ${tools}/tla2tools.jar" | sha256sum -c --status 2>/dev/null; then
    echo "Downloading tla2tools.jar v1.7.4"
    curl -fsSL -o "${tools}/tla2tools.jar.part" "${TLA2TOOLS_URL}"
    echo "${TLA2TOOLS_SHA256}  ${tools}/tla2tools.jar.part" | sha256sum -c --quiet
    mv "${tools}/tla2tools.jar.part" "${tools}/tla2tools.jar"
fi

if [[ ! -x "${tools}/jre/bin/java" && "$(uname -s)-$(uname -m)" == "Linux-x86_64" ]]; then
    echo "Downloading Temurin JRE 25.0.5+8"
    curl -fsSL -o "${tools}/jre.tgz" "${JRE_URL}"
    echo "${JRE_SHA256}  ${tools}/jre.tgz" | sha256sum -c --quiet
    rm -rf "${tools}/jre" && mkdir -p "${tools}/jre"
    tar -xzf "${tools}/jre.tgz" -C "${tools}/jre" --strip-components=1
    rm "${tools}/jre.tgz"
fi

(cd "${repo_root}" && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error)

echo "node:  $(node --version)"
[[ -x "${tools}/jre/bin/java" ]] && echo "java:  $("${tools}/jre/bin/java" -version 2>&1 | head -1)"
echo "tlc:   ${tools}/tla2tools.jar"
echo "pele:  $(node -p "require('${repo_root}/node_modules/pele/package.json').version")"
