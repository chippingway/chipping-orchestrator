# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Git doubles and the collaborator patch table the base-sync tests share."""

from __future__ import annotations

import contextlib
import subprocess
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.base_sync import pre_pr, refresh
from orchestrator.git.publication import probes as publication_probes
from orchestrator.git.verification import probes as verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths


def _git_result(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# Keyword alias -> the one module attribute the alias replaces. Every base-sync
# owner reads its collaborators off the owning module, so each alias has a
# single home and patching an aggregate hub would intercept nothing.
_BASE_SYNC_TARGETS = MappingProxyType(
    {
        "dirty": (_worktree_status, "_worktree_dirty_files"),
        "rebase": (pre_pr, "_rebase_base_into_worktree"),
        "push": (branch_transport, "_push_branch"),
        "head_sha": (verification_probes, "_head_sha"),
        "git": (commands, "_git"),
        "hardened": (commands, "_git_hardened"),
        "fetch": (branch_transport, "_authed_fetch"),
        "ahead_behind": (publication_probes, "_branch_divergence"),
        "target_fetch": (branch_transport, "_authed_target_fetch"),
        "worktrees_root": (paths, "_repo_worktrees_root"),
        "sync": (refresh, "_sync_worktree_with_base"),
    }
)


@contextlib.contextmanager
def _patch_base_sync(**mocks):
    """Patch the base-sync collaborators named by keyword alias for the
    block. Aliases resolve to the module that reads them via
    `_BASE_SYNC_TARGETS`; each value is the object installed in its place.
    Only the named collaborators are patched."""
    with contextlib.ExitStack() as stack:
        for alias, mock in mocks.items():
            module, attribute = _BASE_SYNC_TARGETS[alias]
            stack.enter_context(patch.object(module, attribute, mock))
        yield


def _diverged(ahead: int, behind: int, *, tip: str = "remote-sha"):
    """One divergence reading, as the probe answers it.

    The counts and the head they were taken against travel together, so a
    case that seeds counts is seeding a claim about one commit -- and one
    that seeds none is seeding a reading that never happened, which is what
    `readable=False` says and what no caller may act on.
    """
    return publication_probes._BranchDivergence(
        tip=tip, ahead=ahead, behind=behind, readable=True,
    )
