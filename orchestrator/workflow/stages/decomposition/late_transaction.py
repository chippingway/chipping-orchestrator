# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publish a prepared late split, retire its candidate, and hand work to its children.

Owner checks surround the announcement and supersession. Retirement and
branch reclamation each require the publication to remain superseded, so
a reopened or changed pull request leaves those effects owed.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_retirement as _late_retirement,
    late_split_notices as _late_split_notices,
    late_split_preparation as _late_split_preparation,
    late_supersession as _late_supersession,
    late_supersession_reading as _late_supersession_reading,
    late_supersession_state as _late_supersession_state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateAdjudicationRun, _LateDisposition
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

log = logging.getLogger("orchestrator.workflow")


# What is logged where the barrier past the retirement declines the delete in
# front of it. Not a park: the issue is an umbrella by then and its own
# terminal is what comes back for this, so what the sentence owes an operator
# is the reason and the retry that will take it.
_HELD_BACK_RECLAMATION = (
    "issue=#%d is an umbrella and %s, so branch %s was left on the ledger "
    "rather than deleted behind a change that still points at it; the "
    "umbrella's terminal reclaims it once every child resolves"
)


_UNDONE_SUPERSESSION_PARK = (
    "the committed candidate for this issue was split, its snapshot and "
    "children are safe, and the supersession was made -- but {disagreement}. "
    "So no child was activated and the branch was not reclaimed: the "
    "supersession is what licenses both, and neither may run beside a pull "
    "request that no longer carries it. Reconcile the pull request by hand, "
    "and the next tick supersedes it again and settles the same recorded "
    "verdict."
)


def _published_split(
    context: _LateContext,
    finished: _LateAdjudicationRun,
    plan: _SplitPlan,
    snapshot_ref: str,
) -> _LateAdjudicationRun:
    """Finish a transaction whose children exist: announce, supersede, hand.

    Every step here is one the remote keeps: a comment saying what the parent
    became, the pull request its work is on closed over a supersession notice,
    the umbrella label, and the children this walk lets start. A cycle a close
    ended takes none of them -- what it has already put on the remote is on
    the ledger, and the cleanup path is what settles it, closing that same
    pull request over a cancellation instead.

    So the owner is read BETWEEN them and not once for all of them, on the
    same rule the child loop above runs on: publication is three separate
    moments, each of which is a GitHub round-trip a human can close the issue
    inside. Reading once would let a close observed during the announcement
    or the supersession still hand the parent to `umbrella` and let its
    children loose -- which is the one effect of the whole transaction that
    puts an agent on somebody's repository.

    Each of the three checks leaves the record where the interruption
    actually happened, and the cancellation reads it from there: an ending
    entered at the supersession closes that pull request over a cancellation
    notice, and one entered between the supersession and the
    retirement takes the superseded branch on as owed rather than retiring
    over a branch nothing names.
    """
    stopped = _stopped_publishing(context)
    if stopped is not None:
        return stopped
    _late_split_notices._announced(context, plan, snapshot_ref)
    stopped = _stopped_publishing(context)
    if stopped is not None:
        return stopped
    if not _late_supersession._superseded(context, plan, snapshot_ref):
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    return _retired_split(context, finished, plan)


def _retired_split(
    context: _LateContext,
    finished: _LateAdjudicationRun,
    plan: _SplitPlan,
) -> _LateAdjudicationRun:
    """Hand the parent on, let its children run, and take its branch back.

    Entered with the pull request settled and the children still `blocked`,
    which is the state the third and last owner read is asked from: past it
    an agent runs on somebody's repository, so a close observed anywhere
    between the supersession and here ends the cycle instead.

    The publication is asked again on the same rule and at the same barriers,
    because the supersession is one round-trip and each step below is another:
    a human can reopen, merge, or push to the change between any two of them.
    Every effect here is one nothing takes back -- the children run, the
    pointer is cleared, and the branch behind the pull request is deleted --
    and the supersession is what licenses all three, so each is asked for
    afresh rather than once for the lot.

    What a refusal costs differs by which barrier takes it, and that is the
    retirement's doing. Before it, the answer is a park: the record is still
    live, so the issue stays on `decomposing` with the children blocked and
    the branch intact, and the next tick supersedes the pull request again.
    Past it there is no record left to park -- the write drops the generation
    and hands the issue to `umbrella` -- so what the later barriers do is
    decline the step in front of them and leave it to the retry that owns it:
    the umbrella's own walk for the children, its terminal for the branch.
    Narrower than a park and the strongest thing still available, which is why
    the pre-retirement barrier is placed as the very last thing before that
    write, with the branch resolved ahead of it rather than between.
    """
    stopped = _stopped_publishing(context)
    if stopped is not None:
        return stopped
    # Resolved ahead of the barrier, and ahead of the write that clears
    # `pr_number`: the resolver falls back to the legacy ref while a pull
    # request is recorded, so a second reading after that write could name a
    # different branch from the one this transaction just recorded as owed.
    branch = _naming._resolve_branch_name(
        context.state, context.spec, context.issue.number,
    )
    undone = _late_supersession_reading._publication_holds(context)
    if undone:
        return _late_outcome._finished(
            context, _parked_undone(context, undone),
        )
    ended = _late_retirement._handed_to_children(context, plan, branch)
    if ended is not None:
        return _late_outcome._finished(context, ended)
    _reclaimed_or_held(context, branch)
    return replace(
        finished,
        disposition=_LateDisposition.SETTLED,
        generation=context.generation,
    )


def _parked_undone(
    context: _LateContext, undone: str,
) -> _LateDisposition:
    """Park the pass whose supersession came undone before the retirement."""
    _late_supersession_state._parked_publication(
        context,
        context.generation.published_pr_number,
        undone,
        _UNDONE_SUPERSESSION_PARK,
    )
    return _LateDisposition.PARKED


def _reclaimed_or_held(context: _LateContext, branch: str) -> None:
    """Take the branch back, unless the change pointing at it came back.

    The last irreversible act of the whole road, and the furthest from the
    proof that licensed it: a pinned write, a label write, an owner read, a
    child scan, and one relabel per child all stand in between. So the
    publication is asked once more here, and a pull request that is open again
    keeps its branch -- deleting the ref behind a change somebody reopened is
    the one part of this tail a later pass could never undo.

    Held rather than failed. The obligation went onto the ledger as `pending`
    in the retirement write and stays exactly there, so the umbrella's own
    terminal reclaims it once every child resolves -- which is the retry that
    already owns this, and the reason no typed failure is emitted for a delete
    this pass deliberately never attempted.
    """
    held = _late_supersession_reading._publication_holds(context)
    if not held:
        _late_retirement._reclaimed_branch(context, branch)
        return
    log.error(_HELD_BACK_RECLAMATION, context.issue.number, held, branch)


def _stopped_publishing(
    context: _LateContext,
) -> _LateAdjudicationRun | None:
    """Ask the owner whether the next publication step may happen at all.

    None is the only answer that lets one run, and it is the same guard the
    child loop takes between two creates -- a closed owner ends the cycle
    where it stands, an unreadable one parks with the read owed on the
    record, and neither is a state anything below may publish over.
    """
    still_wanted = _late_owner._still_wanted(context)
    if still_wanted is None:
        return None
    return _late_outcome._finished(context, still_wanted)


def _run_late_split(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Prepare the durable split, then publish and retire it in guarded order."""
    prepared = _late_split_preparation._prepare_split(context, finished)
    if isinstance(prepared, _LateAdjudicationRun):
        return prepared
    return _published_split(
        context, finished, prepared.plan, prepared.snapshot_ref,
    )
