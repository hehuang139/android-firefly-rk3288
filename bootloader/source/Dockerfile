FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc-arm-linux-gnueabihf bison flex bc \
    libssl-dev libgnutls28-dev uuid-dev pkg-config \
    python3 python3-dev python3-setuptools python3-pyelftools swig \
    device-tree-compiler \
    && rm -rf /var/lib/apt/lists/*
