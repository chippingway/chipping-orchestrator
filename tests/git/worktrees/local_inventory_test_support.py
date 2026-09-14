# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Local inventory readings and an unreadable path for clone-attribution cases."""
from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import patch

from orchestrator.git.worktrees import branch_probes, inventory


@contextlib.contextmanager
def _listing(branches):
    """Answer every clone's branch listing with `branches`."""
    with patch.object(
        branch_probes, "_local_orchestrator_branches", return_value=branches,
    ) as listed:
        yield listed


def _scan(*specs):
    """The whole scan over one set of configured repositories."""
    return inventory._local_issue_inventory(specs)


def _found(scanned):
    """Each candidate as the repository and issue it names."""
    return tuple(
        (artifacts.spec.slug, artifacts.issue_number)
        for artifacts in scanned.issues
    )


class _LoopingPath(Path):
    """A clone path whose resolution fails the way a symlink loop fails it.

    A path that raises rather than a loop planted on disk, because what a loop
    costs depends on the interpreter: `Path.resolve` raises `RuntimeError` on
    one under Python 3.12 and answers with the path itself under 3.13. What is
    asserted through this is the handling, which both of them reach.
    """

    def resolve(self, strict: bool = False) -> Path:
        raise RuntimeError(f"Symlink loop from {self}")
