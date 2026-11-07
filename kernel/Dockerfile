FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf bison flex swig libssl-dev libgnutls28-dev python3 python3-dev python3-setuptools device-tree-compiler bc mtools dosfstools fdisk u-boot-tools xz-utils lz4 cpio file ca-certificates curl rsync git && rm -rf /var/lib/apt/lists/*
