# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one reading of the world says about a pending captured completion, and what an applicable one is handed as.

Five answers rather than three, because what a capture that will not go on
is OWED differs, and a caller that could not tell them apart would either
publish stale output, discard paid work on a guess, or strand the issue
behind a hold nothing ends.

APPLICABLE is the only answer that hands the capture on, and the only one
that carries anything: the handoff its road's owner is given
(`AdmittedCompletion`), read over the very readings that admitted it, so the
owner acts on the world that was proved rather than on a second look.

INVALID is a reading that PROVED the capture no longer answers what the
issue now is: the work ended, the issue was moved to another road, the
requirements or a record its handoff froze moved, or the branch, the checkout
head, or the pull request it reported on is another one now; the pull
request, report debt, or adjudication its road answers is gone; or an auto
rebase of that branch was begun and no recovery has ended it, so the branch is
mid-rewrite and its recovery may reset or replace the commit reported on. Its
output may not be published, so it is retired by a guarded invalidation that
keeps which invocation it was.

UNCERTAIN is a reading nobody could take, or one the issue moved under while
it was taken -- a comment, an issue, a thread, a checkout, or a pull request
that would not read, a checkout nothing proves the issue's own or whose head
is no commit the store holds, a record naming no branch live work may use or
claiming a road's record nobody can read, labels or controls that moved
during the dispatch, and an issue, a checkout, or a pull request that moved
between the reading a decision stood on and its effect -- and a run whose
usage was captured unaccounted with no receipt of it read back since.
Nothing proves the capture stale, so it is kept and the tick held for a
later reading.

DAMAGED is a claim nothing here may act on or clear: a capture that will not
read, a cycle identity nobody can name, or a capture of another record or of
a cycle the record has left. It is held, never taken for an absence.

WAITING is a hold the capture waits through without acting: a dependency hold
(`workflow:blocked`), the `workflow:ready` decision that answers it, and an
issue a human took the workflow label off. Each of those stages runs as it
would without a capture, since none of them acts on a developer's work, and
the capture is decided once the issue is back on its road.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import completion_records as _records
from orchestrator.workflow.state import WorkflowLabel


class Standing(StrEnum):
    """Which of the five answers one reading gave."""

    APPLICABLE = "applicable"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"
    DAMAGED = "damaged"
    WAITING = "waiting"


class Reason(StrEnum):
    """Why a reading answered as it did, in the words its log line quotes."""

    # INVALID: the work ended -- the issue closed, or labelled done or rejected.
    ENDED = "the issue's work has ended"
    # INVALID: the issue is on another road than the one the capture reported on.
    RELABELLED = "the issue was moved off the road the capture reported on"
    # INVALID: a record the road's handoff was frozen over has moved since.
    HANDOFF_MOVED = "a record its handoff was frozen over has moved"
    # INVALID: the requirements now read otherwise than the ones the run was handed.
    REQUIREMENTS_MOVED = "the requirements moved since the run was handed them"
    # INVALID: the record pins another branch than the one the capture ran on.
    BRANCH_MOVED = "the record names another branch"
    # INVALID: the checkout stands on another commit than the one reported on.
    CHECKOUT_MOVED = "the checkout moved off the commit the report is about"
    # INVALID: the pull request was merged or closed.
    PULL_REQUEST_ENDED = "the pull request is over"
    # INVALID: the pull request is another branch's, another repository's, or
    # stands on a head neither the run started on nor reported on -- or, under
    # a rewritten-head refresh, on any but the one it reported on.
    PULL_REQUEST_MOVED = "the pull request moved off the run's branch and heads"
    # INVALID: an auto rebase of the branch was begun and no recovery has ended it.
    ANCHORED = "an unfinished auto rebase of its branch stands beside it"
    # INVALID: the pull request, report debt, or adjudication its road answers is gone.
    PREREQUISITE_GONE = "the pull request, report debt, or adjudication its road answers is gone"
    # UNCERTAIN: the pinned comment would not read, or moved since the dispatch read it.
    RECORD_UNREAD = "the pinned comment could not be read as the one the dispatch read"
    # UNCERTAIN: the issue would not read, or its labels or controls moved during the dispatch.
    ISSUE_UNREAD = "the issue's labels and controls could not be read as the dispatch read them"
    # UNCERTAIN: the issue, the checkout, or the pull request moved between a decision's readings and its effect.
    MOVED_BEHIND = "the issue, its checkout, or its pull request moved behind the readings it was decided on"
    # UNCERTAIN: the thread the requirements are read off would not read.
    REQUIREMENTS_UNREAD = "the requirements could not be read"
    # UNCERTAIN: the record names no branch live work may use.
    BRANCH_REFUSED = "the record names no branch live work may use"
    # UNCERTAIN: the checkout is missing, unreadable, or not proven the issue's
    # own, or its head is no commit the store holds.
    CHECKOUT_UNPROVEN = "the checkout the report is about is not proven the issue's own"
    # UNCERTAIN: the pull request the record names would not read.
    PULL_REQUEST_UNREAD = "the pull request could not be read"
    # UNCERTAIN: a record its road answers is claimed in a shape nobody can read.
    PREREQUISITE_UNREAD = "a record its road answers cannot be read"
    # UNCERTAIN: an auto-rebase anchor stands beside it and reads as no commit.
    ANCHOR_UNREAD = "an auto-rebase anchor beside it cannot be read as a commit"
    # UNCERTAIN: its run's usage was captured unaccounted, and no receipt of it reads back.
    ACCOUNTING_UNRESOLVED = "its run's usage accounting has not read back"
    # DAMAGED: the capture, or the cycle it is bound to, reads as nothing this build writes.
    DAMAGED = "the capture or the cycle identity cannot be read"
    # DAMAGED: the capture names another record, or a cycle the record has left.
    NOT_THIS_RECORD = "the capture belongs to another record or workflow cycle"
    # WAITING: a dependency hold, the ready decision, or an unlabeled issue.
    WAITING = "the issue waits on a stage that does not act on a developer's work"


@dataclass(frozen=True)
class AdmittedCompletion:
    """One pending capture its road's owner is handed, with the readings that admitted it.

    `issue` is the issue as its last fetch, right before the handoff, read
    it -- open, and asking for the requirements the run was handed; `label`
    the workflow label the dispatch resolved and that fetch read again;
    `state` the dispatcher's admitted reading, which the capture's read-back
    proved still the comment's. `pull_request_head` is the head the recorded
    pull request stood on when it was read -- the commit the run started on
    or the one it reported on, only the latter for a rewritten-head refresh,
    or on the implementing road the head of a pull request that road reads
    as the `discussion` stage's plan -- or None where the record names no
    pull request yet. Nothing here is a charge, a grant,
    or a park: the owner finishes the capture through the road's existing
    transactions, and every gate those keep -- ownership, size, lease, and
    exact revision -- still applies.
    """

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    label: WorkflowLabel
    state: PinnedState
    capture: _records.CompletionCapture
    pull_request_head: str | None = None

    def refetched(self, issue: Issue) -> AdmittedCompletion:
        """This handoff with `issue` as the one its last fetch answered."""
        return replace(self, issue=issue)


@dataclass(frozen=True)
class Decision:
    """One reading's answer, why, and -- for an APPLICABLE one alone -- the handoff it admitted."""

    standing: Standing
    reason: Reason | None = None
    admitted: AdmittedCompletion | None = None
