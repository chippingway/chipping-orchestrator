# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The git half of a recovery's retry: the candidate it publishes, in its attempt's own terms.

A replay an interrupted tick made and never published is retried by the
workflow (`workflow/engine/rewrite_retry.py`): the transfer permit and the
size gate rule on it before anything is pushed, and the publication is the
git owner's push of exactly that candidate (`rewrite_transport`). What it
publishes is read here -- the candidate the attempt left, over the remote head
the recovery's own fetch verified -- and so is why a landing the retry made
may not be finished. Nothing here decides, pushes, or writes.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    replay_evidence as _replay_evidence,
    rewrite_facts as _rewrite_facts,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.rewrite_handoffs import _RewriteAttempt, _RewriteCandidate
from orchestrator.git.ref_transport import _RefRead

# Why a push that landed could not be finished, in the operator's own terms.
# Spelled at the seam that answers for it rather than beside the park, which
# takes whatever reason its caller established.
_UNROTATED = (
    "the push went out and the verdict did not move with it, so the "
    "permission granted for `{published}` is still outstanding"
)


def _retry_candidate(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> _RewriteCandidate:
    """The candidate a retry of `completed` publishes, read in the attempt's own terms.

    The anchor is the lease, as it was for the push the crash interrupted, so
    a pull request somebody moved off it rejects the retry instead of being
    overwritten. The publication and stage are the ones the attempt recorded
    before git ran, where it recorded them -- the refusals ahead of any retry
    have already held them to the ones this tick reads -- and the tick's own
    for an attempt from before that record existed, which only the counts
    vouched for. The remote is the head the recovery fetched and classified
    the checkout against, and the checkout is read afresh, so a checkout that
    moved since is a candidate naming another commit than the one the
    recovery verified.
    """
    recorded = context.pending_rewrite
    attempt = _RewriteAttempt(
        anchor=context.pending_pre_rebase_sha,
        pr_number=recorded.pr_number if recorded.is_declared else context.pr_number,
        stage=recorded.stage if recorded.is_declared else _replay_evidence._recovered_stage(context.label),
    )
    return _rewrite_facts._prepares_the_candidate(
        context.spec, context.worktree, attempt, completed.branch,
        remote=_RefRead(sha=completed.remote_head),
    )
