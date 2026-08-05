# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12.13
ARG UV_VERSION=0.11.29
ARG AWS_CLI_VERSION=2.36.14
ARG NODE_VERSION=22.22.0

FROM ghcr.io/astral-sh/uv:${UV_VERSION}@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc AS uv
FROM public.ecr.aws/aws-cli/aws-cli:${AWS_CLI_VERSION}@sha256:72180b996fad939e764434d9a69a9512ed699a061cd5db198feeb2e9533fd750 AS awscli
FROM node:${NODE_VERSION}-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94 AS node
FROM python:${PYTHON_VERSION}-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS runtime

ARG TARGETARCH=amd64
ARG KUBECTL_VERSION=v1.36.3
ARG HELM_VERSION=v4.2.3

LABEL org.opencontainers.image.title="diagram-gen"
LABEL org.opencontainers.image.source="https://github.com/anthonyrussano/diagram-generator"
LABEL org.opencontainers.image.description="Reproducible infrastructure diagram generation toolchain"

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    UV_SYSTEM_CERTS=true \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt \
    NPM_CONFIG_CAFILE=/etc/ssl/certs/ca-certificates.crt \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    MERMAID_PUPPETEER_CONFIG=/etc/diagram-gen/puppeteer-config.json

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        chromium \
        curl \
        fontconfig \
        fonts-dejavu-core \
        graphviz \
        less \
        tar \
    && rm -rf /var/lib/apt/lists/*

# Optional public CA certificates can be supplied as BuildKit secrets for
# intercepted corporate networks. They are copied into the image trust store,
# while the source files remain outside the build context and image history.
RUN --mount=type=secret,id=chop_root_ca,required=false \
    --mount=type=secret,id=netskope_root_ca,required=false \
    set -eux; \
    if [ -f /run/secrets/chop_root_ca ]; then \
        install -m 0644 /run/secrets/chop_root_ca /usr/local/share/ca-certificates/chop-root-ca.crt; \
    fi; \
    if [ -f /run/secrets/netskope_root_ca ]; then \
        install -m 0644 /run/secrets/netskope_root_ca /usr/local/share/ca-certificates/netskope-root-ca.crt; \
    fi; \
    update-ca-certificates

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY containers/package.json containers/package-lock.json /opt/mermaid/

RUN set -eux; \
    ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws; \
    ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    case "${TARGETARCH}" in \
        amd64|arm64) tool_arch="${TARGETARCH}" ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${tool_arch}/kubectl"; \
    curl -fsSLO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${tool_arch}/kubectl.sha256"; \
    echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check; \
    install -m 0755 kubectl /usr/local/bin/kubectl; \
    rm kubectl kubectl.sha256; \
    curl -fsSLO "https://get.helm.sh/helm-${HELM_VERSION}-linux-${tool_arch}.tar.gz"; \
    curl -fsSLO "https://get.helm.sh/helm-${HELM_VERSION}-linux-${tool_arch}.tar.gz.sha256sum"; \
    sha256sum --check "helm-${HELM_VERSION}-linux-${tool_arch}.tar.gz.sha256sum"; \
    tar -xzf "helm-${HELM_VERSION}-linux-${tool_arch}.tar.gz"; \
    install -m 0755 "linux-${tool_arch}/helm" /usr/local/bin/helm; \
    rm -rf "linux-${tool_arch}" "helm-${HELM_VERSION}-linux-${tool_arch}.tar.gz" "helm-${HELM_VERSION}-linux-${tool_arch}.tar.gz.sha256sum"; \
    cd /opt/mermaid; \
    npm ci --omit=dev; \
    ln -s /opt/mermaid/node_modules/.bin/mmdc /usr/local/bin/mmdc; \
    npm cache clean --force

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY tests ./tests
COPY examples ./examples
COPY containers/puppeteer-config.json /etc/diagram-gen/puppeteer-config.json

RUN uv sync \
        --frozen \
        --no-editable \
        --extra dev \
        --extra render \
        --extra aws-boto3 \
    && useradd --create-home --uid 1000 --shell /bin/bash diagram \
    && mkdir -p /workspace \
    && mkdir -p /app/.pytest_cache \
    && chown -R diagram:diagram /app/.venv /app/.pytest_cache /app/src \
    && chown diagram:diagram /workspace

ENV PATH="/app/.venv/bin:${PATH}"

USER diagram
WORKDIR /workspace

ENTRYPOINT ["diagram-gen"]
CMD ["--help"]
