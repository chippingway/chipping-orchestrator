# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout and branch a review tick meets unless its case says otherwise.

A reviewer's declared verification is published only once the evidence proof
finds the issue's checkout on this host and the remote branch fetched standing
on the head the reviewer was handed, and an approval waits on that
publication. So a review tick is seeded that way by default: a checkout path
this host holds, and a fetch answering with the head the pinned pull request
stands on as the tick begins. A case about a checkout that is gone, or a
branch that moved, names its own -- through the run options, or by patching
the path itself, which is left standing.
"""
from __future__ import annotations

from unittest.mock import NonCallableMock

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split import payloads as _payloads
from tests.workflow import published_reports as _published_reports
from tests.workflow.repo_values import EXISTING_CHECKOUT


def _seeds_the_review(github, issue, run_options, *, reported: bool) -> None:
    """The world one review tick runs in: the report its delivery published, where `reported`, and the checkout."""
    if reported:
        _published_reports.publishes_the_report(github, issue)
    _stands_on_the_pull_request(github, issue, run_options)


def _stands_on_the_pull_request(github, issue, run_options) -> None:
    """Seed `run_options` with the checkout and fetch a review tick normally meets."""
    if not isinstance(_worktree_paths._worktree_path, NonCallableMock):
        run_options.setdefault("issue_checkout", EXISTING_CHECKOUT)
    pinned = github.pinned_data(issue.number).get("pr_number")
    pull = github.pulls.get(_payloads.as_identity(pinned))
    try:
        head = None if pull is None else pull.head.sha
    except RuntimeError:
        # A pull request whose head will not read is the world the case is
        # about; the tick finds that out for itself.
        return
    if head is not None:
        run_options.setdefault("fetched_branch_tip", head)
