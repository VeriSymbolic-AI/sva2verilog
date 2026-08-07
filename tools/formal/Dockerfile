# syntax=docker/dockerfile:1
FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

ARG TARGETARCH
ARG OSS_CAD_SUITE_RELEASE=2026-07-21

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl xz-utils \
    && case "${TARGETARCH}" in \
         amd64) archive="oss-cad-suite-linux-x64-20260721.tgz"; \
                digest="6efd4012620df0c2305844dfdf9dab7a31763753b9792d6cbb1dcd8327e99d49" ;; \
         arm64) archive="oss-cad-suite-linux-arm64-20260721.tgz"; \
                digest="cca0698fa42d70b895ae09b9fdce055e9ffd8186e204e2c313f6327c9bc59e79" ;; \
         *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 2 ;; \
       esac \
    && curl --fail --location --retry 3 \
         --output /tmp/oss-cad-suite.tgz \
         "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE_RELEASE}/${archive}" \
    && echo "${digest}  /tmp/oss-cad-suite.tgz" | sha256sum --check --strict \
    && tar -xzf /tmp/oss-cad-suite.tgz -C /opt \
    && rm /tmp/oss-cad-suite.tgz \
    && apt-get purge --yes --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/oss-cad-suite/bin:${PATH}"
WORKDIR /work

RUN yosys -V \
    && sby --version \
    && suprove --version >/tmp/suprove-version.txt 2>&1 || test -s /tmp/suprove-version.txt

CMD ["sby", "--help"]
