# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Atheris fuzz targets for the pinned-state and decomposer-manifest parsers.

Each `*_fuzzer.py` is an entry script Atheris runs and ClusterFuzzLite
packages; the target it runs (`pinned_admission`, `manifest_reply`) imports
without Atheris, so the suite replays the committed seeds through it.
`docs/development.md` carries the commands.
"""
