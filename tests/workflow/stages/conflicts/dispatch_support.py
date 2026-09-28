# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Resolving-conflict ticks run the way the dispatcher runs them.

Everything the dispatcher reconciles ahead of a handler runs first -- above all
an approval whose push never got its receipt written, which the reconciliation
pays before any stage may run over it -- and this stage's handler behind it,
exactly as on a live host. A tick with nothing to reconcile runs the handler
just as a direct call would.
"""
from __future__ import annotations

from functools import partial
from pathlib import Path
from unittest.mock import patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import issue_processing as _issue_processing
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.conflicts.conflicts_test_support import _ResolvingConflictMixin

# A checkout this host holds. The reconciliation pays an approval only from a
# checkout it finds on disk; every git reading over it is still the hermetic
# double's.
_EXISTING_CHECKOUT = Path("/tmp")


class _DispatchedConflictMixin(_ResolvingConflictMixin):
    """Conflict scenarios whose every tick is a whole dispatch."""

    def _run_resolving_conflict(self, github, issue, **run_options):
        """One dispatched tick over this issue, on a checkout this host holds."""
        run_options.setdefault("fetched_branch_tip", self.pr_head_sha)
        with patch.object(_worktree_paths, "_worktree_path", return_value=_EXISTING_CHECKOUT):
            return self._run(
                partial(
                    _issue_processing._route_issue_to_handler,
                    github, _TEST_SPEC, issue, github.workflow_label(issue),
                ),
                **run_options,
            )
