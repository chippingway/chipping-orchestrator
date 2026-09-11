# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The push an accepted candidate earns, and the checkout it is handed on with.

Only a verdict taken PAST publication owes a push here, and the reason it is
made on this tick rather than by the stage the issue continues at is that only
this tick still holds the evidence. The verdict was taken against one pull
request standing on one head, the reconciliation ahead of this proved both are
still what they were, and the retirement behind it takes the record that said
so away. The stage resumed afterwards has its own completion to finish and no
way to re-derive any of that -- and two of the five have no publication seam a
resumed tick would even reach. So the branch is put where the verdict said it
may go, named against the accepted commit and pinned to the head the reading
was taken over, and the stage picks up from a pull request that carries it.

A pre-publication verdict pushes nothing: its candidate has no pull request
yet, and the ordinary `implementing` publication it is handed back to is what
opens one. Neither does a retry finishing a settlement whose push already
landed -- the pull request is standing on the accepted candidate, and what is
left to finish is the label and the retirement.

Both of those still owe the CHECKOUT, which is why the proof is on the road out
rather than inside the push. What the verdict licensed is one commit, and the
worktree it was accepted from is writable through the whole adjudication,
through the push itself, and through the tick that died between a landed push
and the retry that finds it.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import (
    late_accepted as _late_accepted,
    late_records as _late_records,
)

log = logging.getLogger("orchestrator.workflow")

_ACCEPTED_PUSH_FAILED_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but it could not be pushed onto the pull request it was measured against "
    "-- so the issue is still under adjudication and nothing has moved. The "
    "verdict is recorded: the next tick pushes the same commit against the "
    "same head, without re-running any agent. A push refused here is usually "
    "the lease doing its job, which means something landed on that pull "
    "request while the adjudication was open."
)

_UNPROVED_CHECKOUT_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change "
    "and `{candidate}` is on the pull request it was measured against, but "
    "the checkout it was accepted from is not standing cleanly on that commit "
    "any more -- so the issue is still under adjudication and the stage it "
    "came from has not been handed the worktree. Every stage past this one "
    "works from that checkout, so one carrying loose edits or an unmeasured "
    "descendant would reach a review, a squash, and a merge with nobody "
    "having read it. Put the worktree back on that commit with a clean "
    "tree and the next tick finishes the settlement, without re-running any "
    "agent."
)


def _pushed_where_it_was_measured(context: _LateContext) -> bool:
    """Put an accepted post-publication candidate on its pull request.

    The push belongs HERE rather than to the stage the issue continues at,
    and the reason is that only this tick still holds the evidence. The
    verdict was taken against one pull request standing on one head; the
    reconciliation a moment ago proved both are still what they were; and the
    retirement behind this takes the record that said so away. The stage
    resumed behind this one has its own work to finish and no way to re-derive
    any of that -- and two of the five have no publication seam a resumed tick
    would even reach.

    So the branch is put where the verdict said it may go, and the stage picks
    up from a pull request that carries the commit. A push that did not land
    parks with the label still on the adjudication: the exemption and the
    approval are already durable, so the retry asks for the same commit
    against the same head and settles from there.

    A pre-publication verdict pushes nothing here. Its candidate has no pull
    request yet, and the `implementing` publication it is handed back to is
    what opens one. Neither does a retry finishing a settlement whose push
    already landed: the reconciliation above found the pull request standing
    on the accepted candidate, so what is left to finish is the label and the
    retirement, not a second push of a commit that is already there.

    Both of those still owe the checkout, which is why the proof below is on
    the road out rather than inside the push: what the verdict licensed is one
    commit, and the worktree it was accepted from is writable through the
    whole adjudication, through the push itself, and through the tick that
    died between a landed push and this retry.
    """
    if not context.generation.has_publication_context:
        return True
    worktree = _worktree_paths._worktree_path(
        context.spec, context.issue.number,
    )
    if not context.already_published and not _accepted_push_landed(
        context, worktree,
    ):
        return False
    return _proved_before_the_handoff(context, worktree)


def _accepted_push_landed(context: _LateContext, worktree) -> bool:
    """Put the accepted commit on its pull request, or park for the retry.

    A push that did not land leaves the label on the adjudication: the
    exemption and the approval are already durable, so the retry asks for the
    same commit against the same head and settles from there.
    """
    if worktree.exists() and _late_accepted._publishes_approved(
        _late_records._gate(
            context.gh, context.spec, context.issue, context.state, worktree,
        ),
        _worktree_paths._resolve_branch_name(
            context.state, context.spec, context.issue.number,
        ),
    ):
        return True
    log.error(
        "issue=#%d could not publish the accepted candidate %s onto PR #%d; "
        "leaving it under adjudication for the retry",
        context.issue.number, context.generation.candidate_sha,
        context.generation.published_pr_number,
    )
    _late_outcome._emit_failure(context, LateFailure.PR_RECONCILE_FAILED)
    _late_parks._park(
        context, _ACCEPTED_PUSH_FAILED_PARK,
        reason=_late_park_state.PARK_PR_UNRECONCILED,
    )
    return False


def _proved_before_the_handoff(context: _LateContext, worktree) -> bool:
    """Refuse the handoff where the checkout is not what the verdict accepted.

    The last thing this settlement owns is the worktree, and the two ticks
    that reach here have left it unwatched for different stretches: the one
    that pushes leaves it writable across the push, the pull-request read, and
    the label; the one finishing an interrupted settlement has left it
    writable since a previous process died. Either way what a human accepted
    is one commit with nothing loose beside it, and every stage the label is
    about to hand this issue to works from the CHECKOUT -- the reviewer reads
    a head ahead of the pushed branch as unpublished work, the squash rewrites
    what is on it, the docs pass commits on top.

    So the publication stands and the handoff stops. The branch carries the
    accepted commit either way, the generation stays live and the label stays
    on the adjudication, and a tick taken once the worktree is back on that
    commit finds the pull request already standing on it and finishes from
    there -- no second push, no agent re-run.

    Reached with a checkout in hand on both roads: a push is made from one or
    not at all, and a recorded verdict is refused for a missing worktree well
    before it is settled.
    """
    if _late_accepted._standing_on(
        worktree, context.generation.candidate_sha,
    ):
        return True
    _late_outcome._emit_failure(context, LateFailure.PR_RECONCILE_FAILED)
    _late_parks._park(
        context,
        _UNPROVED_CHECKOUT_PARK.format(
            candidate=context.generation.candidate_sha,
        ),
        reason=_late_park_state.PARK_PR_UNRECONCILED,
    )
    return False
