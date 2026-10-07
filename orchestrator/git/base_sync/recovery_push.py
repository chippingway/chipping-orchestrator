# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The git half of a recovery's publication: the candidate an interrupted attempt left, in its own terms.

Both roads the workflow takes an interrupted attempt down read it here, over
the remote head the recovery's own fetch verified: the retry of a replay the
crash kept off the pull request (`workflow/engine/rewrite_retry.py`), which
the transfer permit and the size gate rule on before the git owner pushes
exactly that candidate (`rewrite_transport`), and the recovery of a push that
already landed (`workflow/engine/rewrite_landed.py`), which observes where
the remote has it -- or settles an outstanding permission with the leased
no-op -- and hands what it found to the same finish. So is why a landing the
permit was spent on may not be finished. Nothing here decides, pushes, or
writes.
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


def _recovered_candidate(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> _RewriteCandidate:
    """The candidate `completed` stands for, read in the attempt's own terms.

    The anchor is the lease, as it was for the push the crash interrupted, so
    a pull request somebody moved off it rejects a retry instead of being
    overwritten, and it is the head a landing's finish holds the pinned anchor
    to. The publication and stage are the ones the attempt recorded before git
    ran, where it recorded them -- the refusals ahead of either road have
    already held them to the ones this tick reads -- and the tick's own for an
    attempt from before that record existed, which only the counts vouched
    for. The remote is the head the recovery fetched and classified the
    checkout against, and the checkout is read afresh, so a checkout that
    moved since is a candidate naming another commit than the one the recovery
    verified -- which a retry refuses to push and a landing's finish refuses
    to call landed.
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
