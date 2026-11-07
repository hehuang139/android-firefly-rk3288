# SPDX-License-Identifier: Apache-2.0
FROM debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.ustc.edu.cn/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.ustc.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates git git-lfs gnupg curl unzip zip rsync bc \
       build-essential patch bison flex gperf pkg-config cmake ninja-build meson \
       python3 python3-mako python3-yaml python3-jinja2 python3-packaging \
       clang-19 llvm-19-dev libclang-19-dev libclang-cpp19-dev \
       libclc-19 libclc-19-dev libllvmspirvlib-19-dev spirv-tools spirv-headers \
       libdrm-dev libexpat1-dev zlib1g-dev libzstd-dev libssl-dev \
       libncurses-dev libelf-dev libxml2-utils xsltproc fontconfig \
       gcc-multilib g++-multilib libc6-dev-i386 lib32z1-dev \
       dosfstools mtools e2fsprogs device-tree-compiler cpio lz4 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash builder
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gdisk util-linux \
    && rm -rf /var/lib/apt/lists/*
ENV LLVM_CONFIG=/usr/bin/llvm-config-19
USER builder
WORKDIR /work
