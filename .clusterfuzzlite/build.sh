#!/bin/bash -eu
# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
#
# Builds the parser fuzz targets inside the image `Dockerfile` describes; the
# base image's `compile` runs it with `$SRC`, `$OUT`, and `$SANITIZER` set.
#
# The checked-out revision is installed with its runtime and `fuzz` groups
# from `poetry.lock` into the checkout's own `.venv/`, on the CPython 3.12 the
# image compiled, so every package the targets import -- Atheris included -- is
# the one the lock pins and hashes. PyInstaller, which `compile_python_fuzzer`
# packages each target with, and the coverage.py a coverage build bundles are
# build tools rather than dependencies: they are pinned here to the versions
# the base image installs for its own Python, and the base runner reads the
# coverage data of the latter. Each target leaves `$OUT` beside its options,
# its dictionary, and its seed corpus.

project="$SRC/chipping-orchestrator"
fuzz_python=/opt/fuzz-python/bin/python3.12
poetry=/opt/poetry/bin/poetry
targets=(pinned_admission_fuzzer manifest_fuzzer)

cd "$project"
if ! "$fuzz_python" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
  echo "build.sh: $fuzz_python is older than the Python 3.12 this project requires" >&2
  exit 1
fi

env -u VIRTUAL_ENV -u CONDA_PREFIX "$poetry" env use "$fuzz_python"
env -u VIRTUAL_ENV -u CONDA_PREFIX "$poetry" check --lock
env -u VIRTUAL_ENV -u CONDA_PREFIX "$poetry" sync --only main,fuzz --no-interaction
build_tools=("pyinstaller==6.10.0")
if [[ "$SANITIZER" == coverage ]]; then
  build_tools+=("coverage==6.3.2")
fi
.venv/bin/python -m pip install --no-cache-dir "${build_tools[@]}"
# What the targets are packaged on, for the build log.
.venv/bin/python -c 'import importlib.metadata as m, sys; print("Python", sys.version, "atheris", m.version("atheris"))'

# `compile_python_fuzzer` runs `pyinstaller`, and a coverage build's `python3`,
# off PATH.
export PATH="$project/.venv/bin:$PATH"
for target in "${targets[@]}"; do
  compile_python_fuzzer "fuzz/$target.py" --paths "$project"
  cp "fuzz/$target.options" "fuzz/$target.dict" "$OUT/"
  (cd "fuzz/corpus/$target" && find . -type f -print | LC_ALL=C sort |
    zip -q -X -@ "$OUT/${target}_seed_corpus.zip")
done
