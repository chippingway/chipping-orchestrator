# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A copy of this checkout's package laid out the way a wheel installs it."""
from __future__ import annotations

import shutil
from pathlib import Path

# `tests/support/` is two levels beneath the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def installed_copy(site_packages: Path) -> Path:
    """A copy of the package in `site-packages`, the layout a wheel installs."""
    shutil.copytree(
        _REPO_ROOT / "orchestrator",
        site_packages / "orchestrator",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return site_packages
