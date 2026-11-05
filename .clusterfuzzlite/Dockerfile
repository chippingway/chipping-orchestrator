# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
#
# The ClusterFuzzLite build image for the parser fuzz targets under `fuzz/`.
# ClusterFuzzLite builds it from the checkout's root, the context the root
# `.dockerignore` allowlists, and runs the base image's `compile`, which runs
# `build.sh` in the copied checkout. `docs/development.md` covers building and
# running it by hand.

# The upstream Python builder, pinned by digest so a rebuild gets the same
# clang, libFuzzer sanitizer runtimes, `compile_python_fuzzer`, and Ubuntu
# 20.04 userland the packaged targets run against.
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:21f6fab17ace4dc76e1c56de91ee95d3d03da021df94b41056ba036f6c6f55e9

# The builder's own Python is 3.11, under this project's `requires-python`, so
# the targets are built and packaged by a CPython 3.12 compiled here from the
# release tarball python.org publishes, refused unless it matches the digest
# below. Shared, as PyInstaller needs, and found through its rpath.
ARG FUZZ_PYTHON_VERSION=3.12.15
ARG FUZZ_PYTHON_SHA256=c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libbz2-dev libffi-dev liblzma-dev libsqlite3-dev uuid-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && cd /tmp \
    && curl -fsSLO "https://www.python.org/ftp/python/${FUZZ_PYTHON_VERSION}/Python-${FUZZ_PYTHON_VERSION}.tar.xz" \
    && echo "${FUZZ_PYTHON_SHA256}  Python-${FUZZ_PYTHON_VERSION}.tar.xz" | sha256sum --check --strict \
    && tar -xf "Python-${FUZZ_PYTHON_VERSION}.tar.xz" \
    && cd "Python-${FUZZ_PYTHON_VERSION}" \
    && env -u CFLAGS -u CXXFLAGS ./configure --prefix=/opt/fuzz-python --enable-shared \
        LDFLAGS="-Wl,-rpath,/opt/fuzz-python/lib" \
    && env -u CFLAGS -u CXXFLAGS make -j"$(nproc)" \
    && make install \
    && cd / \
    && rm -rf /tmp/Python-*

# Poetry installs the targets' dependencies from `poetry.lock`, in the version
# every workflow in this repository pins, from an environment of its own.
RUN /opt/fuzz-python/bin/python3.12 -m venv /opt/poetry \
    && /opt/poetry/bin/python -m pip install --no-cache-dir "poetry==2.5.1"

COPY . $SRC/chipping-orchestrator
WORKDIR $SRC/chipping-orchestrator
COPY .clusterfuzzlite/build.sh $SRC/
