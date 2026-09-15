# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The push a real remote answers, and the moments a rebase tick can be lost at.

The repository is real and the pull request is a double, so a push that lands
has to move the pull request as well: left disagreeing, every gate past the
first would be entered on a head the remote no longer has.

The crash seams are the other half. Each is the last call a process that never
came back reaches, named for the durable write it stops in front of, so a case
says which window it is about rather than which function it patched. Nothing is
seeded: the tick really rebases, really enters the gate, and really pushes up
to whichever of them the window is about.
"""
from __future__ import annotations

import contextlib
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.base_sync import (
    attempts as _attempts,
    pre_pr as _pre_pr,
    publication as _base_publication,
)
from orchestrator.workflow.stages.implementing import late_transfer_telemetry as _transfer_telemetry
from tests.git.base_sync.real_git_test_support import PR_NUMBER, _LocalBranchPusher

PUSH_BRANCH = "_push_branch"

SET_LABEL = "set_workflow_label"

DIED = "the process died before the tick returned"

# One auto rebase of an adjudicated commit writes these in order: the anchor
# and its terms, the replay git produced, the permission, the push, the
# receipt, the record the sinks are owed, the notice and event, the mark that
# says they went out, the route, and the write that clears the attempt.
BEFORE_THE_REBASE = "before the rebase"
BEFORE_THE_RECORD = "before the record"
AFTER_THE_RECORD = "after the record"
BEFORE_THE_PUSH = "before the push"
BEFORE_THE_RECEIPT = "before the receipt"
BEFORE_THE_REPORT = "before the report"
BEFORE_THE_NOTICE = "before the notice"
BEFORE_THE_MARK = "before the mark"
AT_THE_RELABEL = "at the relabel"
AFTER_THE_RELABEL = "after the relabel"

# The windows a module-level call closes, each stood in for by a raise.
_MODULE_SEAMS = MappingProxyType({
    BEFORE_THE_REBASE: (_pre_pr, "_rebase_base_into_worktree"),
    BEFORE_THE_RECORD: (_attempts, "_records_the_replay"),
    AFTER_THE_RECORD: (_base_publication, "_gated_publication"),
    BEFORE_THE_PUSH: (_branch_transport, PUSH_BRANCH),
    BEFORE_THE_REPORT: (_transfer_telemetry, "_reports_the_transfer"),
    BEFORE_THE_NOTICE: (_base_publication, "_post_auto_rebase_notice"),
    BEFORE_THE_MARK: (_attempts, "_announces"),
})


class PublishesToThePullRequest(_LocalBranchPusher):
    """A push that moves the pull request this fixture's client answers with."""

    def __init__(self, github) -> None:
        super().__init__()
        self._github = github

    def __call__(self, spec, worktree, branch, **options) -> bool:
        """Push, and stand the pull request on whatever the push published."""
        landed = super().__call__(spec, worktree, branch, **options)
        pull_request = self._github.pulls[PR_NUMBER]
        if landed and self.revision:
            pull_request.head = replace(pull_request.head, sha=self.revision)
        return landed


class _LandsThenDies(PublishesToThePullRequest):
    """A push that reaches the remote and whose answer never comes back.

    No seam above the transport can stage this window: the branch really
    moves, and the tick that moved it never learns that it did.
    """

    def __call__(self, spec, worktree, branch, **options) -> bool:
        """Publish the branch, then stop the tick that asked for it."""
        super().__call__(spec, worktree, branch, **options)
        raise RuntimeError(DIED)


class _DiesAfterTheRelabel:
    """A relabel that lands in a process that does not come back."""

    def __init__(self, relabel) -> None:
        self._relabel = relabel

    def __call__(self, issue, label) -> None:
        """Apply the label the finish chose, then stop the tick."""
        self._relabel(issue, label)
        raise RuntimeError(DIED)


def crash_at(github, window: str = ""):
    """The seam a process lost at `window` is last seen at; none for ""."""
    if not window:
        return contextlib.nullcontext()
    seams = {
        **_MODULE_SEAMS,
        BEFORE_THE_RECEIPT: (_branch_transport, PUSH_BRANCH, _LandsThenDies(github)),
        AT_THE_RELABEL: (github, SET_LABEL),
        AFTER_THE_RELABEL: (
            github, SET_LABEL, _DiesAfterTheRelabel(github.set_workflow_label),
        ),
    }
    owner, name, *stand_in = seams[window]
    died = MagicMock(side_effect=RuntimeError(DIED))
    return patch.object(owner, name, stand_in[0] if stand_in else died)
